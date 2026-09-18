from datetime import datetime, timezone

from app.database import async_session_factory
from app.models import Document, DocumentStatus
from app.services.agents.graph import run_clinical_workflow
from app.services.ai.schemas import ClinicalSummary
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

        try:
            state = await run_clinical_workflow(document_id, file_path)
            failure = state.get("failure")
        except Exception as error:
            state = {}
            failure = str(error)

        if failure:
            document.status = DocumentStatus.FAILED.value
            document.error_message = failure
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

        document.updated_at = datetime.now(timezone.utc)
        await session.commit()
