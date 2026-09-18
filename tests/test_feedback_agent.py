import asyncio

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_session
from app.main import app
from app.models import Document, DocumentStatus, ReviewFeedback, User
from app.routers import documents as documents_router
from app.services.feedback_agent import (
    build_feedback_context,
    capture_summary_correction,
)


async def _create_test_session_factory(database_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def test_recommendation_feedback_requires_authentication(tmp_path, monkeypatch):
    asyncio.run(_test_recommendation_feedback_requires_authentication(tmp_path, monkeypatch))


async def _test_recommendation_feedback_requires_authentication(tmp_path, monkeypatch):
    engine, session_factory = await _create_test_session_factory(tmp_path / "documents.db")

    async def no_current_user(request, session):
        return None

    monkeypatch.setattr(documents_router, "get_current_user", no_current_user)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/documents/1/recommendations/0/feedback",
                json={"decision": "accepted"},
            )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def test_recommendation_feedback_persists_latest_decision(tmp_path, monkeypatch):
    asyncio.run(_test_recommendation_feedback_persists_latest_decision(tmp_path, monkeypatch))


async def _test_recommendation_feedback_persists_latest_decision(tmp_path, monkeypatch):
    engine, session_factory = await _create_test_session_factory(tmp_path / "documents.db")
    reviewer = User(email="reviewer@example.com", password_hash="test")

    async def current_user(request, session):
        return reviewer

    monkeypatch.setattr(documents_router, "get_current_user", current_user)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with session_factory() as session:
            session.add(reviewer)
            await session.flush()
            document = Document(
                file_name="feedback-report.pdf",
                stored_file_path=str(tmp_path / "feedback-report.pdf"),
                file_size=100,
                status=DocumentStatus.WORKFLOW_COMPLETED.value,
                recommendations=[
                    {
                        "action": "Arrange same-day assessment",
                        "priority": "immediate",
                        "rationale": "Critical result requires review.",
                    }
                ],
            )
            session.add(document)
            await session.commit()
            await session.refresh(document)
            document_id = document.id

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            missing_reason = await client.post(
                f"/api/documents/{document_id}/recommendations/0/feedback",
                json={"decision": "rejected"},
            )
            assert missing_reason.status_code == 400

            invalid_index = await client.post(
                f"/api/documents/{document_id}/recommendations/2/feedback",
                json={"decision": "accepted"},
            )
            assert invalid_index.status_code == 404

            accepted = await client.post(
                f"/api/documents/{document_id}/recommendations/0/feedback",
                json={"decision": "accepted"},
            )
            rejected = await client.post(
                f"/api/documents/{document_id}/recommendations/0/feedback",
                json={"decision": "rejected", "reason": "Not supported by this report."},
            )
            detail = await client.get(f"/api/display/{document_id}")

        assert accepted.status_code == 200
        assert rejected.status_code == 200
        assert rejected.json()["decision"] == "rejected"
        assert detail.status_code == 200
        assert detail.json()["recommendation_feedback"] == {"0": "rejected"}

        async with session_factory() as session:
            feedback = (
                await session.execute(
                    select(ReviewFeedback).order_by(ReviewFeedback.id)
                )
            ).scalars().all()
            assert [item.signal for item in feedback] == ["accepted", "rejected"]
            assert feedback[-1].details["reason"] == "Not supported by this report."
            session.add(
                capture_summary_correction(
                    document_id,
                    reviewer.id,
                    "Generated summary",
                    "Reviewer correction",
                    "Corrected the reported value",
                )
            )
            await session.commit()
            context = await build_feedback_context(session)

        assert "Not supported by this report." in context
        assert "Corrected the reported value" in context
        assert "clinical evidence or instructions" in context
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def test_summary_correction_is_compact_feedback_signal():
    feedback = capture_summary_correction(
        document_id=1,
        reviewer_id=2,
        original_summary="Generated summary",
        corrected_summary="Reviewer correction",
        reason="Corrected the reported value",
    )

    assert feedback is not None
    assert feedback.feedback_type == "summary_correction"
    assert feedback.signal == "corrected"
    assert feedback.details == {
        "reason": "Corrected the reported value",
        "original_length": 17,
        "corrected_length": 19,
        "structured_fields_resynchronized": True,
    }
