import pytest

from app.services.ai.client import GeminiResponseError
from app.services.ai.schemas import (
    GuidelineCitation,
    LabFinding,
    PatientProfile,
    ReportAnalysis,
)
from app.services.summarise_and_generate_test import summarise_and_generate_test


SUMMARY_PAYLOAD = {
    "headline": "Critically low haemoglobin needs same-day review",
    "summary": "Haemoglobin is 78 g/L against a range of 130 to 175 g/L.",
    "key_points": ["Arrange same-day assessment", "Repeat the full blood count"],
}


def _analysis() -> ReportAnalysis:
    return ReportAnalysis(
        patient=PatientProfile(
            patient_id="PX-1042",
            patient_name="Jordan Ellis",
            date_of_birth="1988-04-12",
            sex="Female",
            encounter_date="2026-03-04",
        ),
        presenting_concern="Persistent fatigue and intermittent dizziness",
        history="Six weeks of symptoms.",
        medications=["Lisinopril 10 mg daily"],
        findings=[
            LabFinding(
                test_name="Haemoglobin",
                value="78",
                unit="g/L",
                reference_range="130 - 175",
                flag="critical",
                interpretation="Severely reduced.",
            )
        ],
    )


def test_summary_agent_returns_structured_summary(fake_gemini_client):
    client = fake_gemini_client(SUMMARY_PAYLOAD)
    citations = [
        GuidelineCitation(
            title="Anaemia Investigation Pathway",
            source="Neuron Clinical Protocol Library",
            section="Escalation",
            excerpt="Haemoglobin below 80 grams per litre requires same-day assessment.",
            score=0.91,
        )
    ]

    summary = summarise_and_generate_test(_analysis(), citations, client=client)

    assert summary.headline.startswith("Critically low haemoglobin")
    assert len(summary.key_points) == 2

    prompt = client.calls[0]["input"]
    assert "Haemoglobin" in prompt
    assert "Anaemia Investigation Pathway" in prompt
    assert "Jordan Ellis" in prompt


def test_summary_agent_rejects_output_that_breaks_the_schema(fake_gemini_client):
    client = fake_gemini_client({"headline": "only a headline"})

    with pytest.raises(GeminiResponseError, match="ClinicalSummary"):
        summarise_and_generate_test(_analysis(), [], client=client)
