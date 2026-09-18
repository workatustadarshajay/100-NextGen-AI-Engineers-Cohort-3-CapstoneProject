import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"


@dataclass(frozen=True)
class AISettings:
    """Runtime configuration for the clinical agent workflow."""

    api_key: str | None
    model: str
    embedding_model: str
    chroma_dir: Path
    guidelines_dir: Path
    synthetic_dir: Path
    collection_name: str
    top_k: int
    request_timeout: float


def _resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


@lru_cache(maxsize=1)
def get_ai_settings() -> AISettings:
    return AISettings(
        api_key=(os.getenv("GEMINI_API_KEY") or "").strip() or None,
        model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
        embedding_model=os.getenv("GEMINI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        chroma_dir=_resolve_path(os.getenv("CHROMA_DIR", "data/chroma")),
        guidelines_dir=_resolve_path(os.getenv("GUIDELINES_DIR", "data/guidelines")),
        synthetic_dir=_resolve_path(os.getenv("SYNTHETIC_DIR", "data/synthetic")),
        collection_name=os.getenv("CHROMA_COLLECTION", "medical_guidelines"),
        top_k=int(os.getenv("RAG_TOP_K", "4")),
        request_timeout=float(os.getenv("GEMINI_TIMEOUT_SECONDS", "90")),
    )
