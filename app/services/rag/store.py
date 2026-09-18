import chromadb
from chromadb.api.models.Collection import Collection

from app.config import get_ai_settings


def get_collection() -> Collection:
    """Return the persistent guideline collection, creating it when absent."""
    settings = get_ai_settings()
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    return client.get_or_create_collection(
        name=settings.collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection() -> Collection:
    """Drop and recreate the guideline collection for a clean ingestion run."""
    settings = get_ai_settings()
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    try:
        client.delete_collection(name=settings.collection_name)
    except Exception:
        # A missing collection is the normal case on a first run.
        pass
    return client.get_or_create_collection(
        name=settings.collection_name,
        metadata={"hnsw:space": "cosine"},
    )
