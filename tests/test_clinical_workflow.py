import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.services.agents.graph as graph_module
import app.services.workflow as workflow_module
from app.database import Base
from app.models import Document, DocumentStatus, Notification
from app.services.ai.schemas import (
    ClinicalSummary,
    GuidelineCitation,
    LabFinding,
    PatientProfile,
    Recommendation,
    ReportAnalysis,
)


def _analysis(flag: str = "critical") -> ReportAnalysis:
    return ReportAnalysis(
        patient=PatientProfile(
            patient_id="PX-1042",
            patient_name="Jordan Ellis",
            date_of_birth="1988-04-12",
            sex="Female",
            encounter_date="2026-03-04",
        ),
        presenting_concern="Persistent fatigue",
        history="Six weeks of symptoms.",
        medications=["Lisinopril 10 mg daily"],
        findings=[
            LabFinding(
                test_name="Haemoglobin",
                value="78",
                unit="g/L",
                reference_range="130 - 175",
                flag=flag,
                interpretation="Severely reduced.",
            )
        ],
    )


def _citations() -> list[GuidelineCitation]:
    return [
        GuidelineCitation(
            title="Anaemia Investigation Pathway",
            source="Neuron Clinical Protocol Library",
            section="Escalation",
            excerpt="Haemoglobin below 80 grams per litre requires same-day assessment.",
            score=0.93,
        )
    ]


def _stub_agents(monkeypatch, analysis: ReportAnalysis) -> None:
    monkeypatch.setattr(graph_module, "extract_from_pdf", lambda path, **kw: analysis)
    monkeypatch.setattr(graph_module, "retrieve_the_docs", lambda query, **kw: _citations())
    monkeypatch.setattr(
        graph_module,
        "summarise_and_generate_test",
        lambda a, c, **kw: ClinicalSummary(
            headline="Critically low haemoglobin", summary="Body text.", key_points=["Escalate"]
        ),
    )
    monkeypatch.setattr(
        graph_module,
        "recommend_follow_ups",
        lambda a, c, s=None, **kw: [
            Recommendation(
                action="Arrange same-day assessment",
                priority="immediate",
                rationale="Below escalation threshold.",
                supporting_titles=["Anaemia Investigation Pathway"],
            )
        ],
    )
    graph_module.get_clinical_graph.cache_clear()


def test_graph_runs_agents_in_sequence(monkeypatch):
    _stub_agents(monkeypatch, _analysis())

    state = asyncio.run(graph_module.run_clinical_workflow(1, "report.pdf"))

    assert state["agent_events"] == [
        "report_analysis",
        "guideline_retrieval",
        "summary",
        "recommendation",
    ]
    assert state["failure"] is None
    assert len(state["citations"]) == 1
    assert state["recommendations"][0].priority == "immediate"
    assert state["review_route"] == "urgent_review"
    assert {event["stage"] for event in state["workflow_events"]} >= {
        "analyze_report",
        "retrieve_guidelines",
        "route_review",
        "prepare_urgent_review",
        "summarise",
        "recommend",
    }


def test_graph_routes_noncritical_findings_to_standard_lane(monkeypatch):
    _stub_agents(monkeypatch, _analysis(flag="high"))

    state = asyncio.run(graph_module.run_clinical_workflow(3, "report.pdf"))

    assert state["failure"] is None
    assert state["review_route"] == "standard_review"
    assert any(
        event["stage"] == "prepare_standard_review"
        for event in state["workflow_events"]
    )


def test_graph_error_handler_records_failure_without_crashing(monkeypatch):
    _stub_agents(monkeypatch, _analysis())

    def explode(path, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(graph_module, "extract_from_pdf", explode)
    graph_module.get_clinical_graph.cache_clear()

    state = asyncio.run(graph_module.run_clinical_workflow(2, "report.pdf"))

    assert state["failure"] == "analyze_report: model unavailable"
    assert state["agent_events"] == ["analyze_report:failed"]
    assert state.get("summary") is None


def _run_workflow_against_temp_db(tmp_path, monkeypatch, analysis):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'workflow.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr(workflow_module, "async_session_factory", factory)
        _stub_agents(monkeypatch, analysis)

        async with factory() as session:
            document = Document(
                file_name="report.pdf",
                stored_file_path=str(tmp_path / "report.pdf"),
                file_size=100,
                status=DocumentStatus.SUMMARISING.value,
            )
            session.add(document)
            await session.commit()
            await session.refresh(document)
            document_id = document.id

        await workflow_module.run_workflow(document_id, str(tmp_path / "report.pdf"))

        async with factory() as session:
            document = await session.get(Document, document_id)
            kinds = [
                row.kind
                for row in (await session.execute(select(Notification))).scalars().all()
            ]
            payload = (
                document.status,
                document.summary,
                document.patient_details,
                document.abnormal_findings,
                document.recommendations,
                document.reference_docs,
                document.error_message,
                document.workflow_stage,
                document.workflow_events,
                document.workflow_attempts,
            )
        await engine.dispose()
        return payload, kinds

    return asyncio.run(scenario())


def test_workflow_persists_structured_agent_output(tmp_path, monkeypatch):
    payload, kinds = _run_workflow_against_temp_db(tmp_path, monkeypatch, _analysis())
    (
        status,
        summary,
        patient,
        findings,
        recommendations,
        citations,
        error,
        workflow_stage,
        workflow_events,
        workflow_attempts,
    ) = payload

    assert status == DocumentStatus.WORKFLOW_COMPLETED.value
    assert error is None
    assert "Critically low haemoglobin" in summary
    assert "- Escalate" in summary
    assert patient["patient_name"] == "Jordan Ellis"
    assert findings[0]["flag"] == "critical"
    assert recommendations[0]["priority"] == "immediate"
    assert citations[0]["title"] == "Anaemia Investigation Pathway"
    assert workflow_stage == "completed"
    assert workflow_attempts == 1
    assert workflow_events[-1]["event"] == "completed"
    assert any(event["stage"] == "retrieve_guidelines" for event in workflow_events)
    assert "processing_completed" in kinds
    assert "critical_finding" in kinds


def test_workflow_skips_critical_notification_when_no_critical_finding(tmp_path, monkeypatch):
    _, kinds = _run_workflow_against_temp_db(tmp_path, monkeypatch, _analysis(flag="high"))

    assert "processing_completed" in kinds
    assert "critical_finding" not in kinds


def test_workflow_marks_document_failed_when_an_agent_fails(tmp_path, monkeypatch):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'failure.db'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr(workflow_module, "async_session_factory", factory)
        _stub_agents(monkeypatch, _analysis())

        def explode(path, **kwargs):
            raise RuntimeError("model unavailable")

        monkeypatch.setattr(graph_module, "extract_from_pdf", explode)
        graph_module.get_clinical_graph.cache_clear()

        async with factory() as session:
            document = Document(
                file_name="report.pdf",
                stored_file_path=str(tmp_path / "report.pdf"),
                file_size=100,
                status=DocumentStatus.SUMMARISING.value,
            )
            session.add(document)
            await session.commit()
            await session.refresh(document)
            document_id = document.id

        await workflow_module.run_workflow(document_id, str(tmp_path / "report.pdf"))

        async with factory() as session:
            document = await session.get(Document, document_id)
            kinds = [
                row.kind
                for row in (await session.execute(select(Notification))).scalars().all()
            ]
            result = (document.status, document.error_message, document.summary)
        await engine.dispose()
        return result, kinds

    (status, error_message, summary), kinds = asyncio.run(scenario())

    assert status == DocumentStatus.FAILED.value
    assert "model unavailable" in error_message
    assert summary is None
    assert kinds == ["processing_failed"]
