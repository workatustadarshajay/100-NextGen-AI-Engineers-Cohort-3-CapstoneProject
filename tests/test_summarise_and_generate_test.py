from inspect import signature

from app.services.summarise_and_generate_test import summarise_and_generate_test


def test_summarise_and_generate_test_accepts_three_inputs_without_history():
    assert list(signature(summarise_and_generate_test).parameters) == [
        "patient_details",
        "medical_details",
        "reference_docs",
    ]

    summary = summarise_and_generate_test(
        {"patient_name": "Jordan Ellis"},
        {
            "presenting_concern": "Persistent fatigue and intermittent dizziness",
            "history": "This history should stay out of the generated summary",
            "medications": "Lisinopril 10 mg daily; vitamin D supplement",
        },
        [
            {
                "title": "Primary care follow-up pathway",
                "source": "Neuron clinical protocol library",
                "relevance": "Suggested review path.",
            }
        ],
    )

    assert "Clinical synthesis for Jordan Ellis" in summary
    assert "Persistent fatigue and intermittent dizziness" in summary
    assert "Lisinopril 10 mg daily; vitamin D supplement" in summary
    assert "Primary care follow-up pathway" in summary
    assert "This history should stay out of the generated summary" not in summary
    assert "Context" not in summary
