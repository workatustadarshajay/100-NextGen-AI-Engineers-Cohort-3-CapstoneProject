from app.services.ai.client import generate_structured
from app.services.ai.prompts import SUMMARY_SYSTEM, format_citations, format_findings
from app.services.ai.schemas import ClinicalSummary, GuidelineCitation, ReportAnalysis


def summarise_and_generate_test(
    analysis: ReportAnalysis,
    reference_docs: list[GuidelineCitation],
    *,
    client=None,
) -> ClinicalSummary:
    """Summary Agent: write the clinician-facing summary of an analysed report."""
    patient = analysis.patient
    prompt = (
        f"Patient: {patient.patient_name} (ID {patient.patient_id}, "
        f"born {patient.date_of_birth}, sex {patient.sex})\n"
        f"Encounter date: {patient.encounter_date}\n"
        f"Presenting concern: {analysis.presenting_concern}\n"
        f"History: {analysis.history}\n"
        f"Medications: {', '.join(analysis.medications) or 'none recorded'}\n\n"
        "Abnormal findings:\n"
        f"{format_findings(analysis.abnormal_findings)}\n\n"
        "Retrieved guideline excerpts:\n"
        f"{format_citations(reference_docs)}"
    )
    return generate_structured(ClinicalSummary, prompt, SUMMARY_SYSTEM, client=client)
