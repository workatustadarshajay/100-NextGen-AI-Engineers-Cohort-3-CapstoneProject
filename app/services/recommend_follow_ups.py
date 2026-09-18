from app.services.ai.client import generate_structured
from app.services.ai.prompts import (
    RECOMMENDATION_SYSTEM,
    format_citations,
    format_findings,
)
from app.services.ai.schemas import (
    ClinicalSummary,
    GuidelineCitation,
    Recommendation,
    RecommendationSet,
    ReportAnalysis,
)


def recommend_follow_ups(
    analysis: ReportAnalysis,
    reference_docs: list[GuidelineCitation],
    summary: ClinicalSummary | None = None,
    *,
    feedback_context: str = "",
    client=None,
) -> list[Recommendation]:
    """Recommendation Agent: propose guideline-backed follow-up actions."""
    feedback_section = (
        "\n\n--- BEGIN REVIEWER FEEDBACK PROFILE ---\n"
        f"{feedback_context}\n"
        "--- END REVIEWER FEEDBACK PROFILE ---"
        if feedback_context
        else ""
    )
    prompt = (
        f"Presenting concern: {analysis.presenting_concern}\n"
        f"History: {analysis.history}\n"
        f"Medications: {', '.join(analysis.medications) or 'none recorded'}\n"
        f"Critical finding present: {'yes' if analysis.has_critical_finding else 'no'}\n\n"
        f"Summary headline: {summary.headline if summary else 'not available'}\n\n"
        "Abnormal findings:\n"
        f"{format_findings(analysis.abnormal_findings)}\n\n"
        "Retrieved guideline excerpts:\n"
        f"{format_citations(reference_docs)}"
        f"{feedback_section}"
    )
    result = generate_structured(
        RecommendationSet, prompt, RECOMMENDATION_SYSTEM, client=client
    )
    citation_titles = {citation.title for citation in reference_docs}
    for recommendation in result.recommendations:
        recommendation.supporting_titles = [
            title
            for title in recommendation.supporting_titles
            if title in citation_titles
        ]
    return result.recommendations
