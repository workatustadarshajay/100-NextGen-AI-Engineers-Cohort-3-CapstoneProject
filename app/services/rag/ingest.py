from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from app.config import get_ai_settings
from app.services.ai.client import embed_texts
from app.services.rag.store import reset_collection


CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
EMBED_BATCH = 32


@dataclass(frozen=True)
class GuidelineChunk:
    chunk_id: str
    text: str
    title: str
    source: str
    section: str


def read_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _split_sections(body: str) -> list[tuple[str, str]]:
    """Group lines under their nearest heading, detected as a short unpunctuated line."""
    sections: list[tuple[str, list[str]]] = []
    current_heading = "Overview"
    current_lines: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        is_heading = len(line) < 45 and not line.endswith(".") and not line[0].isdigit()
        if is_heading:
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = line
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_heading, current_lines))
    return [(heading, " ".join(lines)) for heading, lines in sections if lines]


def _split_chunks(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return [chunk for chunk in chunks if chunk]


def build_chunks(path: Path) -> list[GuidelineChunk]:
    text = read_pdf_text(path)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    title = lines[0]
    source = next(
        (line.split(":", 1)[1].strip() for line in lines[:5] if line.lower().startswith("source:")),
        path.stem.replace("-", " ").title(),
    )
    body = "\n".join(line for line in lines[1:] if not line.lower().startswith("source:"))

    chunks: list[GuidelineChunk] = []
    for section_index, (heading, section_text) in enumerate(_split_sections(body)):
        for chunk_index, chunk_text in enumerate(_split_chunks(section_text)):
            chunks.append(
                GuidelineChunk(
                    chunk_id=f"{path.stem}:{section_index}:{chunk_index}",
                    text=chunk_text,
                    title=title,
                    source=source,
                    section=heading,
                )
            )
    return chunks


def ingest_guidelines(paths: list[Path] | None = None) -> int:
    """Rebuild the guideline index and return the number of stored chunks."""
    settings = get_ai_settings()
    pdf_paths = sorted(paths or settings.guidelines_dir.glob("*.pdf"))
    if not pdf_paths:
        raise FileNotFoundError(
            f"No guideline PDFs found in {settings.guidelines_dir}. "
            "Run scripts/generate_synthetic_data.py first."
        )

    chunks: list[GuidelineChunk] = []
    for path in pdf_paths:
        chunks.extend(build_chunks(path))
    if not chunks:
        return 0

    collection = reset_collection()
    for start in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[start : start + EMBED_BATCH]
        embeddings = embed_texts(
            [f"title: {chunk.title} | text: {chunk.text}" for chunk in batch],
            task_type="RETRIEVAL_DOCUMENT",
        )
        collection.upsert(
            ids=[chunk.chunk_id for chunk in batch],
            documents=[chunk.text for chunk in batch],
            embeddings=embeddings,
            metadatas=[
                {"title": chunk.title, "source": chunk.source, "section": chunk.section}
                for chunk in batch
            ],
        )
    return len(chunks)
