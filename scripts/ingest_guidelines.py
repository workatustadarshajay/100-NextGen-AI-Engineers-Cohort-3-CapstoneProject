"""Chunk, embed, and index the medical guideline PDFs into ChromaDB."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_ai_settings
from app.services.ai.client import MissingGeminiKeyError
from app.services.rag.ingest import ingest_guidelines


def main() -> int:
    settings = get_ai_settings()
    try:
        count = ingest_guidelines()
    except MissingGeminiKeyError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Indexed {count} guideline chunks into {settings.chroma_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
