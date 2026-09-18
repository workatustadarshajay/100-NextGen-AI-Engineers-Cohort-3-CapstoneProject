from pathlib import Path

from pypdf import PdfReader

from app.services.ai.client import generate_structured
from app.services.ai.prompts import REPORT_ANALYSIS_SYSTEM
from app.services.ai.schemas import ReportAnalysis


MAX_REPORT_CHARS = 60_000


def _read_pdf_pages(file_path: str) -> list[str]:
    reader = PdfReader(str(file_path))
    return [(page.extract_text() or "").strip() for page in reader.pages]


def read_pdf_text(file_path: str) -> str:
    """Return the plain text of a PDF, joined across pages."""
    return "\n".join(_read_pdf_pages(file_path)).strip()


def _normalise_source_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _finding_source(finding, pages: list[str]) -> tuple[int | None, str]:
    test_name = _normalise_source_text(finding.test_name)
    value = _normalise_source_text(finding.value)
    if not test_name or not value:
        return None, ""

    for page_number, page_text in enumerate(pages, start=1):
        normalized_page = _normalise_source_text(page_text)
        if test_name not in normalized_page or value not in normalized_page:
            continue
        for line in page_text.splitlines():
            normalized_line = _normalise_source_text(line)
            if test_name in normalized_line and value in normalized_line:
                return page_number, line.strip()[:500]
        return page_number, page_text[:500].strip()
    return None, ""


def _attach_finding_sources(analysis: ReportAnalysis, pages: list[str]) -> ReportAnalysis:
    for finding in analysis.findings:
        finding.source_page, finding.source_excerpt = _finding_source(finding, pages)
    return analysis


def extract_from_pdf(file_path: str, *, client=None) -> ReportAnalysis:
    """Report Analysis Agent: turn a clinical PDF into structured findings."""
    pages = _read_pdf_pages(file_path)
    report_text = "\n".join(pages).strip()
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
    analysis = generate_structured(ReportAnalysis, prompt, REPORT_ANALYSIS_SYSTEM, client=client)
    return _attach_finding_sources(analysis, pages)
