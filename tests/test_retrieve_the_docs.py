from app.services.retrieve_the_docs import retrieve_the_docs


def test_retrieve_the_docs_returns_relevant_references():
    references = retrieve_the_docs(
        {"presenting_concern": "Persistent fatigue and intermittent dizziness"}
    )

    assert len(references) == 3
    assert [reference["title"] for reference in references] == [
        "Primary care follow-up pathway",
        "Medication and symptom review guide",
        "Routine laboratory monitoring checklist",
    ]
    assert all(set(reference) == {"title", "source", "relevance"} for reference in references)
    assert "persistent fatigue and intermittent dizziness" in references[0]["relevance"]
