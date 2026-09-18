from app.services.ai.schemas import (
    ClinicalSummary,
    GuidelineCitation,
    LabFinding,
    PatientProfile,
    ReportAnalysis,
)
from app.services.recommend_follow_ups import recommend_follow_ups


RECOMMENDATION_PAYLOAD = {
    "recommendations": [
        {
            "action": "Arrange same-day clinical assessment",
            "priority": "immediate",
            "rationale": "Haemoglobin is below the 80 g/L escalation threshold.",
            "supporting_titles": ["Anaemia Investigation Pathway", "Invented source"],
        },
        {
            "action": "Request ferritin and iron studies",
            "priority": "urgent",
            "rationale": "Iron deficiency must be confirmed before treatment.",
            "supporting_titles": ["Anaemia Investigation Pathway"],
        },
    ]
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
        presenting_concern="Persistent fatigue",
        history="Six weeks of symptoms.",
        medications=[],
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


def test_recommendation_agent_returns_prioritised_actions(fake_gemini_client):
    client = fake_gemini_client(RECOMMENDATION_PAYLOAD)
    citations = [
        GuidelineCitation(
            title="Anaemia Investigation Pathway",
            source="Neuron Clinical Protocol Library",
            section="Escalation",
            excerpt="Haemoglobin below 80 grams per litre requires same-day assessment.",
            score=0.93,
        )
    ]
    summary = ClinicalSummary(headline="Low haemoglobin", summary="...", key_points=[])

    recommendations = recommend_follow_ups(_analysis(), citations, summary, client=client)

    assert [item.priority for item in recommendations] == ["immediate", "urgent"]
    assert recommendations[0].supporting_titles == ["Anaemia Investigation Pathway"]

    prompt = client.calls[0]["input"]
    assert "Critical finding present: yes" in prompt
    assert "Anaemia Investigation Pathway" in prompt


def test_recommendation_agent_receives_bounded_reviewer_feedback(fake_gemini_client):
    client = fake_gemini_client(RECOMMENDATION_PAYLOAD)
    feedback_context = (
        "Reviewer feedback profile from prior reviews:\n"
        "- Recently rejected recommendation patterns:\n"
        "  - Request ferritin and iron studies (reviewer reason: Not supported by this report.)"
    )

    recommend_follow_ups(
        _analysis(),
        [],
        feedback_context=feedback_context,
        client=client,
    )

    prompt = client.calls[0]["input"]
    assert "BEGIN REVIEWER FEEDBACK PROFILE" in prompt
    assert "Not supported by this report." in prompt
