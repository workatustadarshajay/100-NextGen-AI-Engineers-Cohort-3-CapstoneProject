import asyncio
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_session
from app.main import app
from app.models import Document, DocumentAssignment, DocumentStatus, Notification, User, utc_now
from app.routers import dashboard as dashboard_router
from app.routers import documents as documents_router
from app.routers import notifications as notifications_router
from app.services.ai.schemas import ClinicalSummary, PatientProfile, ReportAnalysis
from app.services.analytics import get_dashboard_metrics
from app.services.notifications import ensure_overdue_notifications
from app.services import workflow as workflow_service


async def _create_test_session_factory(database_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def test_operations_workflow(tmp_path, monkeypatch):
    asyncio.run(_test_operations_workflow(tmp_path, monkeypatch))


async def _test_operations_workflow(tmp_path, monkeypatch):
    upload_directory = tmp_path / "uploads"
    upload_directory.mkdir()
    removable_file = upload_directory / "failed.pdf"
    removable_file.write_bytes(b"pdf")
    monkeypatch.setattr(documents_router, "UPLOADS_DIR", upload_directory)

    engine, session_factory = await _create_test_session_factory(tmp_path / "documents.db")

    async def override_get_session():
        async with session_factory() as session:
            yield session

    async def fake_current_user(request, session):
        return await session.scalar(select(User).where(User.email == "owner@example.com"))

    monkeypatch.setattr(documents_router, "get_current_user", fake_current_user)
    monkeypatch.setattr(dashboard_router, "get_current_user", fake_current_user)
    monkeypatch.setattr(notifications_router, "get_current_user", fake_current_user)
    app.dependency_overrides[get_session] = override_get_session

    try:
        async with session_factory() as session:
            owner = User(email="owner@example.com", password_hash="hash")
            reviewer = User(email="reviewer@example.com", password_hash="hash")
            session.add_all([owner, reviewer])
            await session.flush()
            ready = Document(
                file_name="ready.pdf",
                stored_file_path=str(upload_directory / "ready.pdf"),
                file_size=100,
                status=DocumentStatus.WORKFLOW_COMPLETED.value,
                summary="Ready summary",
            )
            failed = Document(
                file_name="failed.pdf",
                stored_file_path=str(removable_file),
                file_size=100,
                status=DocumentStatus.FAILED.value,
                error_message="Workflow failed",
            )
            session.add_all([ready, failed])
            await session.commit()
            await session.refresh(ready)
            await session.refresh(failed)
            ready_id = ready.id
            failed_id = failed.id
            reviewer_id = reviewer.id
            session.add(
                DocumentAssignment(document_id=failed_id, user_id=reviewer_id)
            )
            session.add(
                Notification(
                    document_id=failed_id,
                    kind="processing_failed",
                    title="Processing failed",
                    message="Failed document needs attention.",
                )
            )
            await session.commit()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            reviewers_response = await client.get("/api/reviewers")
            assert reviewers_response.status_code == 200
            assert len(reviewers_response.json()) == 2

            assign_response = await client.post(
                "/api/documents/bulk",
                json={"document_ids": [ready_id], "action": "assign", "assignee_id": reviewer_id},
            )
            assert assign_response.status_code == 200
            assert assign_response.json()["affected_count"] == 1

            mark_response = await client.post(
                "/api/documents/bulk",
                json={"document_ids": [ready_id], "action": "mark_reviewed"},
            )
            assert mark_response.status_code == 200
            assert mark_response.json()["affected_count"] == 1

            export_response = await client.post(
                "/api/documents/export", json={"document_ids": [ready_id, failed_id]}
            )
            assert export_response.status_code == 200
            assert "attachment" in export_response.headers["content-disposition"]
            assert "ready.pdf" in export_response.text
            assert "failed.pdf" in export_response.text

            dashboard_response = await client.get("/api/dashboard")
            dashboard_payload = dashboard_response.json()
            assert dashboard_response.status_code == 200
            assert dashboard_payload["total_documents"] == 2
            assert dashboard_payload["completed_documents"] == 1
            assert dashboard_payload["outstanding_documents"] == 1
            assert dashboard_payload["failed_workflows"] == 1
            assert dashboard_payload["reviewer_workloads"][0]["assigned_count"] == 2

            notification_response = await client.get("/api/notifications")
            notification_payload = notification_response.json()
            assert notification_response.status_code == 200
            assert notification_payload["unread_count"] >= 1
            assert any(item["kind"] == "document_submitted" for item in notification_payload["notifications"])

            notification_id = notification_payload["notifications"][0]["id"]
            read_response = await client.post(f"/api/notifications/{notification_id}/read")
            assert read_response.status_code == 200
            assert read_response.json()["read_at"] is not None

            read_all_response = await client.post("/api/notifications/read-all")
            assert read_all_response.status_code == 200
            assert read_all_response.json()["updated"] >= 0

            dashboard_page_response = await client.get("/dashboard")
            assert dashboard_page_response.status_code == 200
            assert "Needs attention" in dashboard_page_response.text

            delete_response = await client.post(
                "/api/documents/bulk",
                json={"document_ids": [failed_id], "action": "delete"},
            )
            assert delete_response.status_code == 200
            assert delete_response.json()["affected_count"] == 1

        assert not removable_file.exists()
        async with session_factory() as session:
            assert await session.get(Document, failed_id) is None
            assert await session.scalar(
                select(DocumentAssignment).where(DocumentAssignment.document_id == failed_id)
            ) is None
            assert await session.scalar(
                select(Notification).where(Notification.document_id == failed_id)
            ) is None
            assignment = await session.scalar(
                select(DocumentAssignment).where(DocumentAssignment.document_id == ready_id)
            )
            assert assignment.user_id == reviewer_id
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def test_operations_require_authentication(tmp_path):
    asyncio.run(_test_operations_require_authentication(tmp_path))


async def _test_operations_require_authentication(tmp_path):
    engine, session_factory = await _create_test_session_factory(tmp_path / "documents.db")

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            api_requests = [
                client.get("/api/display"),
                client.get("/api/display/1"),
                client.get("/api/documents/1/pdf"),
                client.get("/api/documents/1/download"),
                client.get("/api/documents/1/workflow-events"),
                client.get("/api/reviewers"),
                client.get("/api/dashboard"),
                client.get("/api/notifications"),
                client.post(
                    "/api/upload",
                    files={"file": ("report.pdf", b"%PDF-1.4")},
                ),
                client.post("/api/summarise/1"),
                client.patch("/api/edit/1", json={"summary": "probe"}),
                client.post("/api/submit/1"),
                client.delete("/api/documents/1"),
                client.post(
                    "/api/documents/bulk",
                    json={"document_ids": [1], "action": "mark_reviewed"},
                ),
                client.post("/api/documents/export", json={"document_ids": [1]}),
            ]
            page_requests = [
                client.get("/documents"),
                client.get("/upload"),
                client.get("/dashboard"),
            ]
            api_responses, page_responses = await asyncio.gather(
                asyncio.gather(*api_requests), asyncio.gather(*page_requests)
            )
            assert all(response.status_code == 401 for response in api_responses)
            assert all(response.status_code == 303 for response in page_responses)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def test_workflow_events_and_overdue_notifications(tmp_path, monkeypatch):
    asyncio.run(_test_workflow_events_and_overdue_notifications(tmp_path, monkeypatch))


async def _test_workflow_events_and_overdue_notifications(tmp_path, monkeypatch):
    engine, session_factory = await _create_test_session_factory(tmp_path / "documents.db")
    monkeypatch.setattr(workflow_service, "async_session_factory", session_factory)

    async def fake_clinical_workflow(_document_id, _file_path):
        return {
            "analysis": ReportAnalysis(
                patient=PatientProfile(
                    patient_id="PX-1",
                    patient_name="Patient",
                    date_of_birth="1980-01-01",
                    sex="Female",
                    encounter_date="2026-01-01",
                ),
                presenting_concern="Condition",
                history="History",
                medications=[],
                findings=[],
            ),
            "summary": ClinicalSummary(
                headline="Generated summary", summary="Body", key_points=[]
            ),
            "citations": [],
            "recommendations": [],
            "failure": None,
        }

    monkeypatch.setattr(workflow_service, "run_clinical_workflow", fake_clinical_workflow)

    try:
        async with session_factory() as session:
            completed_document = Document(
                file_name="completed.pdf",
                stored_file_path=str(tmp_path / "completed.pdf"),
                file_size=100,
                status=DocumentStatus.SUMMARISING.value,
            )
            overdue_document = Document(
                file_name="overdue.pdf",
                stored_file_path=str(tmp_path / "overdue.pdf"),
                file_size=100,
                status=DocumentStatus.WORKFLOW_COMPLETED.value,
                updated_at=utc_now() - timedelta(hours=49),
            )
            session.add_all([completed_document, overdue_document])
            await session.commit()
            await session.refresh(completed_document)
            await session.refresh(overdue_document)
            completed_id = completed_document.id
            overdue_id = overdue_document.id

        await workflow_service.run_workflow(completed_id, str(tmp_path / "completed.pdf"))
        async with session_factory() as session:
            completed_notification = await session.scalar(
                select(Notification).where(
                    Notification.document_id == completed_id,
                    Notification.kind == "processing_completed",
                )
            )
            completed_document = await session.get(Document, completed_id)
            assert completed_document.status == DocumentStatus.WORKFLOW_COMPLETED.value
            assert completed_notification is not None

            await ensure_overdue_notifications(session)
            await ensure_overdue_notifications(session)
            overdue_notifications = (
                await session.execute(
                    select(Notification).where(
                        Notification.document_id == overdue_id,
                        Notification.kind == "review_overdue",
                    )
                )
            ).scalars().all()
            assert len(overdue_notifications) == 1
    finally:
        await engine.dispose()


def test_dashboard_processing_time_ignores_review_delay(tmp_path):
    asyncio.run(_test_dashboard_processing_time_ignores_review_delay(tmp_path))


async def _test_dashboard_processing_time_ignores_review_delay(tmp_path):
    engine, session_factory = await _create_test_session_factory(tmp_path / "metrics.db")
    workflow_started = utc_now() - timedelta(minutes=7)
    workflow_completed = workflow_started + timedelta(minutes=2)

    try:
        async with session_factory() as session:
            session.add(
                Document(
                    file_name="review-delay.pdf",
                    stored_file_path=str(tmp_path / "review-delay.pdf"),
                    file_size=100,
                    status=DocumentStatus.HITL_COMPLETED.value,
                    workflow_started_at=workflow_started,
                    workflow_completed_at=workflow_completed,
                    updated_at=workflow_completed + timedelta(hours=12),
                )
            )
            await session.commit()

            metrics = await get_dashboard_metrics(session)

        assert metrics.average_processing_minutes == 2.0
        assert metrics.processed_today == 1
    finally:
        await engine.dispose()
