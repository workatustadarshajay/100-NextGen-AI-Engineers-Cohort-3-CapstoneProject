from app.config import get_ai_settings
from app.services.ai.client import embed_texts
from app.services.ai.schemas import GuidelineCitation
from app.services.rag.store import get_collection
from app.services.trusted_guideline_search import search_trusted_guidelines


def retrieve_the_docs(
    query: str,
    top_k: int | None = None,
    *,
    collection=None,
    client=None,
    trusted_search=None,
) -> list[GuidelineCitation]:
    """Return the guideline excerpts most relevant to the analysed report."""
    cleaned_query = (query or "").strip()
    if not cleaned_query:
        return []

    settings = get_ai_settings()
    active_collection = collection if collection is not None else get_collection()
    available = active_collection.count()
    if available == 0:
        if not settings.trusted_search_enabled:
            return []
        search = trusted_search or search_trusted_guidelines
        return search(cleaned_query, limit=settings.trusted_search_limit)

    limit = min(top_k or settings.top_k, available)
    [query_embedding] = embed_texts(
        [f"task: search result | query: {cleaned_query}"],
        task_type="RETRIEVAL_QUERY",
        client=client,
    )
    result = active_collection.query(query_embeddings=[query_embedding], n_results=limit)

    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    citations: list[GuidelineCitation] = []
    for excerpt, metadata, distance in zip(documents, metadatas, distances):
        metadata = metadata or {}
        score = round(1.0 - float(distance), 4)
        if score < settings.min_relevance_score:
            continue
        citations.append(
            GuidelineCitation(
                title=str(metadata.get("title", "Untitled guideline")),
                source=str(metadata.get("source", "Neuron guideline library")),
                section=str(metadata.get("section", "")),
                excerpt=excerpt or "",
                score=score,
            )
        )
    if citations or not settings.trusted_search_enabled:
        return citations
    return (trusted_search or search_trusted_guidelines)(
        cleaned_query,
        limit=settings.trusted_search_limit,
    )
