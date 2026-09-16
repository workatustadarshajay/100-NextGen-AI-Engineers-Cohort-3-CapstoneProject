def summarise_and_generate_test(
    patient_details: dict[str, str],
    medical_details: dict[str, str],
    reference_docs: list[dict[str, str]],
) -> str:
    """Create the generated summary from the three workflow inputs."""
    patient_name = patient_details.get("patient_name", "the patient")
    concern = medical_details.get("presenting_concern", "the reported concern")
    medications = medical_details.get("medications", "No medications supplied")
    reference_titles = ", ".join(document["title"] for document in reference_docs)

    return (
        f"Clinical synthesis for {patient_name}\n\n"
        f"Presenting concern\n{concern}\n\n"
        f"Current medications\n{medications}\n\n"
        "Recommended review\n"
        "Confirm symptom duration, review hydration and medication adherence, and "
        "consider the next routine laboratory panel with the supervising clinician.\n\n"
        "Generated review checks\n"
        "- Confirm the patient identity and document date.\n"
        "- Reconcile current medication and recent changes.\n"
        "- Record follow-up actions and escalation criteria.\n\n"
        f"Reference set\n{reference_titles}"
    )
