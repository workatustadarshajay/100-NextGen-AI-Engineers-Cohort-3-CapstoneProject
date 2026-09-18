import pytest

from app.services.extract_from_pdf import extract_from_pdf, read_pdf_text


ANALYSIS_PAYLOAD = {
    "patient": {
        "patient_id": "PX-1042",
        "patient_name": "Jordan Ellis",
        "date_of_birth": "1988-04-12",
        "sex": "Female",
        "encounter_date": "2026-03-04",
    },
    "presenting_concern": "Persistent fatigue and intermittent dizziness",
    "history": "Symptoms reported over the last six weeks.",
    "medications": ["Lisinopril 10 mg daily"],
    "findings": [
        {
            "test_name": "Haemoglobin",
            "value": "78",
            "unit": "g/L",
            "reference_range": "130 - 175",
            "flag": "critical",
            "interpretation": "Severely reduced haemoglobin.",
        },
        {
            "test_name": "Platelets",
            "value": "250",
            "unit": "x10^9/L",
            "reference_range": "150 - 400",
            "flag": "normal",
            "interpretation": "Within the reference range.",
        },
    ],
}


def test_read_pdf_text_returns_page_text(make_pdf):
    path = make_pdf("report.pdf", ["Neuron Clinical Laboratory Report", "Haemoglobin 78 g/L"])

    text = read_pdf_text(str(path))

    assert "Neuron Clinical Laboratory Report" in text
    assert "Haemoglobin 78 g/L" in text


def test_extract_from_pdf_returns_structured_analysis(make_pdf, fake_gemini_client):
    path = make_pdf("report.pdf", ["Patient ID: PX-1042", "Haemoglobin 78 g/L"])
    client = fake_gemini_client(ANALYSIS_PAYLOAD)

    analysis = extract_from_pdf(str(path), client=client)

    assert analysis.patient.patient_name == "Jordan Ellis"
    assert len(analysis.findings) == 2
    assert [finding.test_name for finding in analysis.abnormal_findings] == ["Haemoglobin"]
    assert analysis.has_critical_finding is True
    assert analysis.findings[0].source_page == 1
    assert analysis.findings[0].source_excerpt == "Haemoglobin 78 g/L"

    request = client.calls[0]
    assert "PX-1042" in request["input"]
    assert request["response_format"]["mime_type"] == "application/json"


def test_extract_from_pdf_rejects_a_pdf_without_text(make_pdf, fake_gemini_client):
    path = make_pdf("blank.pdf", [])

    with pytest.raises(ValueError, match="No readable text"):
        extract_from_pdf(str(path), client=fake_gemini_client(ANALYSIS_PAYLOAD))
