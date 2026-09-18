from pathlib import Path

from pypdf import PdfReader

from app.services.ai.client import generate_structured
from app.services.ai.prompts import REPORT_ANALYSIS_SYSTEM
from app.services.ai.schemas import ReportAnalysis


MAX_REPORT_CHARS = 60_000


def read_pdf_text(file_path: str) -> str:
    """Return the plain text of a PDF, joined across pages."""
    reader = PdfReader(str(file_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def extract_from_pdf(file_path: str, *, client=None) -> ReportAnalysis:
    """Report Analysis Agent: turn a clinical PDF into structured findings."""
    report_text = read_pdf_text(file_path)
    if not report_text:
        raise ValueError(
            f"No readable text found in {Path(file_path).name}. "
            "Scanned or image-only PDFs are not supported."
        )

    prompt = (
        f"Clinical report file name: {Path(file_path).name}\n\n"
        "Analyse the following clinical report and return the structured result.\n\n"
        "--- BEGIN REPORT ---\n"
        f"{report_text[:MAX_REPORT_CHARS]}\n"
        "--- END REPORT ---"
    )
    return generate_structured(ReportAnalysis, prompt, REPORT_ANALYSIS_SYSTEM, client=client)
