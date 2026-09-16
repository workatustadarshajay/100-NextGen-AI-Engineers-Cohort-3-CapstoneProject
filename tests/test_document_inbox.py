import asyncio

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_session
from app.main import app
from app.models import Document, DocumentStatus
from app.routers import documents as documents_router


async def _create_test_session_factory(database_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def test_display_filters_by_filename_and_status(tmp_path):
    asyncio.run(_test_display_filters_by_filename_and_status(tmp_path))


async def _test_display_filters_by_filename_and_status(tmp_path):
    engine, session_factory = await _create_test_session_factory(tmp_path / "documents.db")
    documents = [
        Document(
            file_name="alpha-intake.pdf",
            stored_file_path=str(tmp_path / "alpha-intake.pdf"),
            file_size=100,
            status=DocumentStatus.WORKFLOW_COMPLETED.value,
        ),
        Document(
            file_name="beta-intake.pdf",
            stored_file_path=str(tmp_path / "beta-intake.pdf"),
            file_size=100,
            status=DocumentStatus.FAILED.value,
        ),
    ]

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with session_factory() as session:
            session.add_all(documents)
            await session.commit()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            search_response = await client.get(
                "/api/display", params={"search": "alpha", "page_size": 50}
            )
            search_payload = search_response.json()
            assert search_response.status_code == 200
            assert search_payload["total"] == 1
            assert search_payload["items"][0]["file_name"] == "alpha-intake.pdf"
            assert search_payload["counts"] == {"workflowcompleted": 1}

            status_response = await client.get(
                "/api/display", params={"status": "failed", "page_size": 5}
            )
            status_payload = status_response.json()
            assert status_response.status_code == 200
            assert status_payload["total"] == 1
            assert status_payload["items"][0]["file_name"] == "beta-intake.pdf"
            assert status_payload["counts"] == {"failed": 1}
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def test_failed_document_can_be_requeued(monkeypatch, tmp_path):
    asyncio.run(_test_failed_document_can_be_requeued(monkeypatch, tmp_path))


async def _test_failed_document_can_be_requeued(monkeypatch, tmp_path):
    engine, session_factory = await _create_test_session_factory(tmp_path / "documents.db")
    called = []

    async def fake_run_workflow(document_id, file_path):
        called.append((document_id, file_path))

    monkeypatch.setattr(documents_router, "run_workflow", fake_run_workflow)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with session_factory() as session:
            document = Document(
                file_name="failed-intake.pdf",
                stored_file_path=str(tmp_path / "failed-intake.pdf"),
                file_size=100,
                status=DocumentStatus.FAILED.value,
                error_message="Extraction failed",
            )
            session.add(document)
            await session.commit()
            await session.refresh(document)
            document_id = document.id
            stored_path = document.stored_file_path

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(f"/api/summarise/{document_id}")
            payload = response.json()

        assert response.status_code == 200
        assert payload["status"] == DocumentStatus.SUMMARISING.value
        assert called == [(document_id, stored_path)]
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
