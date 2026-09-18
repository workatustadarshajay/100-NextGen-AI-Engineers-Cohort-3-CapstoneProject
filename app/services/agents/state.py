from operator import add
from typing import Any, Annotated, TypedDict

from app.services.ai.schemas import (
    ClinicalSummary,
    GuidelineCitation,
    Recommendation,
    ReportAnalysis,
)


class ClinicalWorkflowState(TypedDict, total=False):
    """State passed between the clinical agents.

    `agent_events` accumulates because every node appends to it.
    """

    document_id: int
    file_path: str
    analysis: ReportAnalysis | None
    citations: list[GuidelineCitation]
    summary: ClinicalSummary | None
    recommendations: list[Recommendation]
    agent_events: Annotated[list[str], add]
    workflow_events: Annotated[list[dict[str, Any]], add]
    review_route: str
    feedback_context: str
    failure: str | None
