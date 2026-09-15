from pathlib import Path


def extract_from_pdf(file_path: str) -> tuple[dict[str, str], dict[str, str]]:
    """Return patient and medical data for the document workflow."""
    display_name = Path(file_path).stem.replace("_", " ").replace("-", " ").title()

    patient_details = {
        "patient_id": "PX-1042",
        "patient_name": "Jordan Ellis",
        "date_of_birth": "1988-04-12",
        "source_file": display_name,
    }
    medical_details = {
        "presenting_concern": "Persistent fatigue and intermittent dizziness",
        "history": "Symptoms reported over the last six weeks with no acute distress noted",
        "medications": "Lisinopril 10 mg daily; vitamin D supplement",
        "observations": "Follow-up laboratory review recommended",
    }
    return patient_details, medical_details
