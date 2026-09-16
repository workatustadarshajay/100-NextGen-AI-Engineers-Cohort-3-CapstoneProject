from app.services.extract_from_pdf import extract_from_pdf


def test_extract_from_pdf_returns_expected_details(tmp_path):
    patient_details, medical_details = extract_from_pdf(
        str(tmp_path / "patient_intake.pdf")
    )

    assert patient_details == {
        "patient_id": "PX-1042",
        "patient_name": "Jordan Ellis",
        "date_of_birth": "1988-04-12",
        "source_file": "Patient Intake",
    }
    assert medical_details == {
        "presenting_concern": "Persistent fatigue and intermittent dizziness",
        "history": "Symptoms reported over the last six weeks with no acute distress noted",
        "medications": "Lisinopril 10 mg daily; vitamin D supplement",
        "observations": "Follow-up laboratory review recommended",
    }
