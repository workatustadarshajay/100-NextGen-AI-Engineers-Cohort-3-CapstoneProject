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


def test_authenticated_pdf_preview_and_download(tmp_path, monkeypatch):
    asyncio.run(_test_authenticated_pdf_preview_and_download(tmp_path, monkeypatch))


async def _test_authenticated_pdf_preview_and_download(tmp_path, monkeypatch):
    upload_directory = tmp_path / "uploads"
    upload_directory.mkdir()
    pdf_path = upload_directory / "source-report.pdf"
    pdf_bytes = b"%PDF-1.4\nNeuron source report\n%%EOF\n"
    pdf_path.write_bytes(pdf_bytes)
    monkeypatch.setattr(documents_router, "UPLOADS_DIR", upload_directory)

    async def fake_current_user(request, session):
        return object()

    monkeypatch.setattr(documents_router, "get_current_user", fake_current_user)
    engine, session_factory = await _create_test_session_factory(tmp_path / "documents.db")

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with session_factory() as session:
            document = Document(
                file_name="source-report.pdf",
                stored_file_path=str(pdf_path),
                file_size=len(pdf_bytes),
                status=DocumentStatus.WORKFLOW_COMPLETED.value,
            )
            session.add(document)
            await session.commit()
            await session.refresh(document)
            document_id = document.id

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            preview_response = await client.get(f"/api/documents/{document_id}/pdf")
            download_response = await client.get(f"/api/documents/{document_id}/download")

        assert preview_response.status_code == 200
        assert preview_response.content == pdf_bytes
        assert preview_response.headers["content-type"] == "application/pdf"
        assert preview_response.headers["content-disposition"].startswith("inline;")

        assert download_response.status_code == 200
        assert download_response.content == pdf_bytes
        assert download_response.headers["content-disposition"].startswith("attachment;")
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
