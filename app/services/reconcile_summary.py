import json
from typing import Any

from app.services.ai.client import generate_structured
from app.services.ai.prompts import RECONCILIATION_SYSTEM
from app.services.ai.schemas import SummaryReconciliation


def _format_context(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def reconcile_summary(
    edited_summary: str,
    *,
    patient_details: dict[str, Any] | None,
    medical_details: dict[str, Any] | None,
    abnormal_findings: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    reference_docs: list[dict[str, Any]],
    client=None,
    fallback_client=None,
) -> SummaryReconciliation:
    """Reconcile persisted structured fields without rerunning PDF ingestion."""
    prompt = (
        "Reconcile the structured clinical fields against the reviewer-edited summary. "
        "Return a complete replacement object for every structured field in the response schema.\n\n"
        "--- BEGIN EDITED SUMMARY ---\n"
        f"{edited_summary}\n"
        "--- END EDITED SUMMARY ---\n\n"
        "--- BEGIN EXISTING STRUCTURED CONTEXT ---\n"
        f"Patient details: {_format_context(patient_details or {})}\n"
        f"Medical details: {_format_context(medical_details or {})}\n"
        f"Abnormal findings: {_format_context(abnormal_findings)}\n"
        f"Recommendations: {_format_context(recommendations)}\n"
        f"Guideline citations: {_format_context(reference_docs)}\n"
        "--- END EXISTING STRUCTURED CONTEXT ---\n\n"
        "The edited summary is authoritative for reviewer corrections. Keep unsupported values "
        "unchanged when possible, and use 'unknown' instead of guessing."
    )
    result = generate_structured(
        SummaryReconciliation,
        prompt,
        RECONCILIATION_SYSTEM,
        client=client,
        fallback_client=fallback_client,
    )

    result.abnormal_findings = [
        finding for finding in result.abnormal_findings if finding.flag != "normal"
    ]
    citation_titles = {
        str(citation.get("title"))
        for citation in reference_docs
        if citation.get("title")
    }
    for recommendation in result.recommendations:
        recommendation.supporting_titles = [
            title
            for title in recommendation.supporting_titles
            if title in citation_titles
        ]
    return result