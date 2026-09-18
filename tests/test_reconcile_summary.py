import asyncio
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_session
from app.main import app
from app.models import Document, DocumentStatus
from app.routers import documents as documents_router
from app.services.ai.client import GeminiResponseError
from app.services.ai.schemas import (
    GuidelineCitation,
    LabFinding,
    PatientProfile,
    Recommendation,
    ReconciledMedicalDetails,
    SummaryReconciliation,
)
from app.services.reconcile_summary import reconcile_summary


RECONCILIATION_PAYLOAD = {
    "patient": {
        "patient_id": "PX-1042",
        "patient_name": "Jordan Ellis",
        "date_of_birth": "1988-04-12",
        "sex": "Female",
        "encounter_date": "2026-03-04",
    },
    "medical_details": {
        "presenting_concern": "Persistent fatigue",
        "history": "Six weeks of symptoms.",
        "medications": ["Lisinopril 10 mg daily"],
        "headline": "Critically low haemoglobin",
        "key_points": ["Same-day assessment is needed"],
    },
    "abnormal_findings": [
        {
            "test_name": "Haemoglobin",
            "value": "78",
            "unit": "g/L",
            "reference_range": "130 - 175",
            "flag": "critical",
            "interpretation": "Severely reduced.",
        },
        {
            "test_name": "Sodium",
            "value": "140",
            "unit": "mmol/L",
            "reference_range": "135 - 145",
            "flag": "normal",
            "interpretation": "Within range.",
        }
    ],
    "recommendations": [
        {
            "action": "Arrange same-day assessment",
            "priority": "immediate",
            "rationale": "The haemoglobin is critically low.",
            "supporting_titles": ["Anaemia Investigation Pathway", "Invented source"],
        }
    ],
}


def _reconciled_result() -> SummaryReconciliation:
    return SummaryReconciliation.model_validate(RECONCILIATION_PAYLOAD)


def test_reconcile_summary_validates_context_and_known_citations(fake_gemini_client):
    client = fake_gemini_client(RECONCILIATION_PAYLOAD)
    result = reconcile_summary(
        "Corrected summary: arrange same-day assessment.",
        patient_details={"patient_name": "Jordan Ellis"},
        medical_details={"presenting_concern": "Persistent fatigue"},
        abnormal_findings=[{"test_name": "Haemoglobin", "flag": "critical"}],
        recommendations=[],
        reference_docs=[
            {
                "title": "Anaemia Investigation Pathway",
                "source": "Neuron Clinical Protocol Library",
            }
        ],
        client=client,
    )

    assert result.patient.patient_name == "Jordan Ellis"
    assert result.abnormal_findings[0].flag == "critical"
    assert len(result.abnormal_findings) == 1
    assert result.recommendations[0].supporting_titles == ["Anaemia Investigation Pathway"]
    assert "Corrected summary" in client.calls[0]["input"]
    assert "existing structured context" in client.calls[0]["input"].lower()


def test_reconcile_summary_rejects_invalid_model_output(fake_gemini_client):
    client = fake_gemini_client({"patient": {"patient_id": "PX-1"}})

    with pytest.raises(GeminiResponseError, match="SummaryReconciliation"):
        reconcile_summary(
            "Edited summary",
            patient_details=None,
            medical_details=None,
            abnormal_findings=[],
            recommendations=[],
            reference_docs=[],
            client=client,
        )


async def _create_test_session_factory(database_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def test_edit_document_persists_reconciled_fields(tmp_path, monkeypatch):
    asyncio.run(_test_edit_document_persists_reconciled_fields(tmp_path, monkeypatch))


async def _test_edit_document_persists_reconciled_fields(tmp_path, monkeypatch):
    engine, session_factory = await _create_test_session_factory(tmp_path / "documents.db")
    monkeypatch.setattr(documents_router, "reconcile_summary", lambda *args, **kwargs: _reconciled_result())

    async def fake_current_user(request, session):
        return SimpleNamespace(id=1)

    monkeypatch.setattr(documents_router, "get_current_user", fake_current_user)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with session_factory() as session:
            document = Document(
                file_name="report.pdf",
                stored_file_path=str(tmp_path / "report.pdf"),
                file_size=100,
                status=DocumentStatus.WORKFLOW_COMPLETED.value,
                summary="Original summary",
                patient_details={"patient_name": "Old name"},
                medical_details={"presenting_concern": "Old concern"},
                reference_docs=[
                    {
                        "title": "Anaemia Investigation Pathway",
                        "source": "Neuron Clinical Protocol Library",
                    }
                ],
                abnormal_findings=[{"test_name": "Old test"}],
                recommendations=[{"action": "Old action"}],
            )
            session.add(document)
            await session.commit()
            await session.refresh(document)
            document_id = document.id

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.patch(
                f"/api/edit/{document_id}",
                json={"summary": "Corrected summary"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"] == "Corrected summary"
        assert payload["patient_details"]["patient_name"] == "Jordan Ellis"
        assert payload["medical_details"]["headline"] == "Critically low haemoglobin"
        assert payload["abnormal_findings"][0]["flag"] == "critical"
        assert payload["recommendations"][0]["priority"] == "immediate"
        assert payload["citations"][0]["title"] == "Anaemia Investigation Pathway"

        async with session_factory() as session:
            saved = await session.get(Document, document_id)
            assert saved.summary == "Corrected summary"
            assert saved.patient_details["patient_name"] == "Jordan Ellis"
            assert saved.abnormal_findings[0]["flag"] == "critical"
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def test_edit_document_does_not_save_when_reconciliation_fails(tmp_path, monkeypatch):
    asyncio.run(_test_edit_document_does_not_save_when_reconciliation_fails(tmp_path, monkeypatch))


async def _test_edit_document_does_not_save_when_reconciliation_fails(tmp_path, monkeypatch):
    engine, session_factory = await _create_test_session_factory(tmp_path / "documents.db")

    async def fake_current_user(request, session):
        return SimpleNamespace(id=1)

    monkeypatch.setattr(documents_router, "get_current_user", fake_current_user)

    def fail_reconciliation(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(documents_router, "reconcile_summary", fail_reconciliation)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with session_factory() as session:
            document = Document(
                file_name="report.pdf",
                stored_file_path=str(tmp_path / "report.pdf"),
                file_size=100,
                status=DocumentStatus.WORKFLOW_COMPLETED.value,
                summary="Original summary",
                patient_details={"patient_name": "Original patient"},
                abnormal_findings=[{"test_name": "Original test"}],
            )
            session.add(document)
            await session.commit()
            await session.refresh(document)
            document_id = document.id

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.patch(
                f"/api/edit/{document_id}",
                json={"summary": "Attempted replacement"},
            )

        assert response.status_code == 503
        assert "not saved" in response.json()["detail"]
        assert "synchronized" in response.json()["detail"]

        async with session_factory() as session:
            saved = await session.get(Document, document_id)
            assert saved.summary == "Original summary"
            assert saved.patient_details == {"patient_name": "Original patient"}
            assert saved.abnormal_findings == [{"test_name": "Original test"}]
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()