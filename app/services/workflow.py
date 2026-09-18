from datetime import datetime, timezone
from inspect import signature

from app.database import async_session_factory
from app.models import Document, DocumentStatus, utc_now
from app.observability import log_workflow_event, make_workflow_event, safe_error_message
from app.services.agents.graph import run_clinical_workflow
from app.services.ai.schemas import ClinicalSummary
from app.services.feedback_agent import build_feedback_context
from app.services.notifications import add_notification


def compose_summary_text(summary: ClinicalSummary) -> str:
    """Render the agent summary as the editable text a reviewer sees."""
    lines = [summary.headline, "", summary.summary]
    if summary.key_points:
        lines.extend(["", "Key points"])
        lines.extend(f"- {point}" for point in summary.key_points)
    return "\n".join(lines).strip()


async def run_workflow(document_id: int, file_path: str) -> None:
    """Run the clinical agent graph and persist its structured output."""
    async with async_session_factory() as session:
        document = await session.get(Document, document_id)
        if document is None or document.status == DocumentStatus.HITL_COMPLETED.value:
            return

        existing_events = list(document.workflow_events or [])
        started_at = datetime.now(timezone.utc)
        attempt = (document.workflow_attempts or 0) + 1
        document.workflow_attempts = attempt
        document.workflow_stage = "starting"
        document.workflow_started_at = started_at
        document.workflow_completed_at = None
        document.error_message = None
        document.workflow_events = [
            make_workflow_event("workflow", "started", attempt=attempt)
        ]
        document.updated_at = started_at
        await session.commit()
        log_workflow_event(
            20,
            "workflow_started",
            document_id=document_id,
            stage="workflow",
            attempt=attempt,
        )

        async def persist_update(node_name: str, update: dict) -> None:
            events = update.get("workflow_events") or []
            if not events:
                return
            try:
                document.workflow_events = [*(document.workflow_events or []), *events]
                latest_event = events[-1]
                document.workflow_stage = str(latest_event.get("stage") or node_name)
                document.updated_at = utc_now()
                await session.commit()
                log_workflow_event(
                    20,
                    "stage_persisted",
                    document_id=document_id,
                    stage=document.workflow_stage,
                    attempt=latest_event.get("attempt"),
                    duration_ms=latest_event.get("duration_ms"),
                )
            except Exception as error:
                await session.rollback()
                log_workflow_event(
                    30,
                    "telemetry_persist_failed",
                    document_id=document_id,
                    stage=node_name,
                    error=error,
                )

        try:
            workflow_parameters = signature(run_clinical_workflow).parameters
            workflow_kwargs = (
                {"on_update": persist_update}
                if "on_update" in workflow_parameters
                else {}
            )
            if "feedback_context" in workflow_parameters:
                workflow_kwargs["feedback_context"] = await build_feedback_context(session)
            state = await run_clinical_workflow(document_id, file_path, **workflow_kwargs)
            failure = state.get("failure")
        except Exception as error:
            state = {}
            failure = f"workflow: {safe_error_message(error)}"
            log_workflow_event(
                40,
                "workflow_crashed",
                document_id=document_id,
                stage="workflow",
                attempt=attempt,
                error=error,
            )

        finished_at = datetime.now(timezone.utc)
        duration_ms = (finished_at - started_at).total_seconds() * 1_000
        workflow_events = list(state.get("workflow_events") or [])

        if failure:
            failure_message = safe_error_message(RuntimeError(str(failure)))
            document.status = DocumentStatus.FAILED.value
            document.error_message = failure_message
            document.workflow_stage = "failed"
            document.workflow_events = [
                *existing_events,
                *workflow_events,
                make_workflow_event(
                    "workflow",
                    "failed",
                    duration_ms=duration_ms,
                    attempt=attempt,
                    message=failure_message,
                    error_type="WorkflowError",
                ),
            ]
            log_workflow_event(
                40,
                "workflow_failed",
                document_id=document_id,
                stage="workflow",
                attempt=attempt,
                duration_ms=duration_ms,
                error=RuntimeError(failure_message),
            )
            await add_notification(
                session,
                kind="processing_failed",
                title="Processing failed",
                message=f"{document.file_name} needs attention before it can be reviewed.",
                document_id=document.id,
            )
        else:
            analysis = state["analysis"]
            summary = state["summary"]
            citations = state.get("citations") or []
            recommendations = state.get("recommendations") or []

            document.summary = compose_summary_text(summary)
            document.patient_details = analysis.patient.model_dump()
            document.medical_details = {
                "presenting_concern": analysis.presenting_concern,
                "history": analysis.history,
                "medications": analysis.medications,
                "headline": summary.headline,
                "key_points": summary.key_points,
            }
            document.reference_docs = [citation.model_dump() for citation in citations]
            document.abnormal_findings = [
                finding.model_dump() for finding in analysis.abnormal_findings
            ]
            document.recommendations = [item.model_dump() for item in recommendations]
            document.status = DocumentStatus.WORKFLOW_COMPLETED.value
            document.error_message = None
            document.workflow_stage = "completed"
            document.workflow_events = [
                *existing_events,
                *workflow_events,
                make_workflow_event(
                    "workflow",
                    "completed",
                    duration_ms=duration_ms,
                    attempt=attempt,
                ),
            ]

            log_workflow_event(
                20,
                "workflow_completed",
                document_id=document_id,
                stage="workflow",
                attempt=attempt,
                duration_ms=duration_ms,
            )

            await add_notification(
                session,
                kind="processing_completed",
                title="Processing completed",
                message=f"{document.file_name} is ready for review.",
                document_id=document.id,
            )
            if analysis.has_critical_finding:
                await add_notification(
                    session,
                    kind="critical_finding",
                    title="Critical finding detected",
                    message=f"{document.file_name} contains a critical result. Prioritise this review.",
                    document_id=document.id,
                )

        document.workflow_completed_at = finished_at
        document.updated_at = finished_at
        await session.commit()
