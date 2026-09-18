from operator import add
from typing import Annotated, TypedDict

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
    failure: str | None
