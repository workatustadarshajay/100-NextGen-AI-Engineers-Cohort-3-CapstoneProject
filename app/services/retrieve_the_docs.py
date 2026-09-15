
def retrieve_the_docs(medical_details: dict[str, str]) -> list[dict[str, str]]:
    """Return relevant reference material for the medical details."""
    concern = medical_details.get("presenting_concern", "the presenting concern")
    return [
        {
            "title": "Primary care follow-up pathway",
            "source": "Neuron clinical protocol library",
            "relevance": f"Suggested review path for {concern.lower()}.",
        },
        {
            "title": "Medication and symptom review guide",
            "source": "Neuron medication safety library",
            "relevance": "Supports reconciliation and follow-up question generation.",
        },
        {
            "title": "Routine laboratory monitoring checklist",
            "source": "Neuron diagnostics library",
            "relevance": "Provides a structured checklist for the next clinical review.",
        },
    ]
