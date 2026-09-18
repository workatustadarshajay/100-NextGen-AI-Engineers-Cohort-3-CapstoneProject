from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import date, datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from app.config import get_ai_settings
from app.services.ai.schemas import GuidelineCitation


LOGGER = logging.getLogger("neuron.guideline_search")
SEARCH_ENDPOINT = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
TRUSTED_HOST = "www.ebi.ac.uk"
MAX_QUERY_LENGTH = 300
MAX_RESULT_LIMIT = 5


def _clean_text(value: object, limit: int) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())[:limit]


def classify_freshness(publication_date: str, *, today: date | None = None) -> str:
    """Label age for review context; age alone does not invalidate guidance."""
    if not publication_date:
        return "unknown"
    match = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", publication_date)
    if not match:
        return "unknown"
    year, month, day = (int(value) if value else 1 for value in match.groups())
    try:
        published = date(year, month, day)
    except ValueError:
        return "unknown"
    current = today or datetime.now(timezone.utc).date()
    if published > current:
        return "unknown"
    age_days = (current - published).days
    if age_days <= 365 * 3:
        return "current"
    if age_days <= 365 * 5:
        return "aging"
    return "old"


def _source_url(result: dict[str, Any]) -> str:
    pmid = re.sub(r"\D", "", _clean_text(result.get("pmid"), 32))
    if pmid:
        return f"https://europepmc.org/article/MED/{pmid}"
    return ""


def _rank_score(index: int, result_count: int) -> float:
    if result_count <= 1:
        return 1.0
    return round(max(0.5, 1.0 - index / (result_count * 2)), 4)


def _request_json(
    query: str,
    *,
    limit: int,
    timeout: float,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    parsed_endpoint = urlparse(SEARCH_ENDPOINT)
    if parsed_endpoint.scheme != "https" or parsed_endpoint.hostname != TRUSTED_HOST:
        raise ValueError("Trusted guideline search endpoint is not allowlisted")
    params = urlencode(
        {
            "query": f'({query}) AND (guideline OR "practice guideline" OR consensus OR protocol)',
            "format": "json",
            "resultType": "core",
            "pageSize": limit,
        }
    )
    request = Request(
        f"{SEARCH_ENDPOINT}?{params}",
        headers={
            "Accept": "application/json",
            "User-Agent": "NeuronClinicalOps/1.0 guideline-retrieval",
        },
    )
    active_opener = opener or urlopen
    with active_opener(request, timeout=timeout) as response:
        body = response.read(1_000_000)
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Trusted guideline search returned an invalid response")
    return payload


def search_trusted_guidelines(
    query: str,
    *,
    limit: int | None = None,
    timeout: float | None = None,
    opener: Callable[..., Any] | None = None,
) -> list[GuidelineCitation]:
    """Search Europe PMC for guideline-like records without sending patient identifiers."""
    cleaned_query = _clean_text(query, MAX_QUERY_LENGTH)
    if not cleaned_query:
        return []

    settings = get_ai_settings()
    result_limit = min(max(limit or settings.trusted_search_limit, 1), MAX_RESULT_LIMIT)
    request_timeout = timeout or settings.trusted_search_timeout
    try:
        payload = _request_json(
            cleaned_query,
            limit=result_limit,
            timeout=request_timeout,
            opener=opener,
        )
    except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as error:
        LOGGER.warning("trusted_guideline_search_failed: %s", error)
        return []

    results = payload.get("resultList", {}).get("result", [])
    if isinstance(results, dict):
        results = [results]
    if not isinstance(results, list):
        return []

    citations: list[GuidelineCitation] = []
    seen_titles: set[str] = set()
    for index, raw_result in enumerate(results[:result_limit]):
        if not isinstance(raw_result, dict):
            continue
        title = _clean_text(raw_result.get("title"), 500)
        excerpt = _clean_text(raw_result.get("abstractText"), 2_000)
        if not title or not excerpt or title.casefold() in seen_titles:
            continue
        seen_titles.add(title.casefold())
        published = _clean_text(
            raw_result.get("firstPublicationDate") or raw_result.get("pubYear"), 32
        )
        journal = _clean_text(raw_result.get("journalTitle"), 160)
        citations.append(
            GuidelineCitation(
                title=title,
                source="Europe PMC / PubMed",
                section=journal or "External guideline record",
                excerpt=excerpt,
                score=_rank_score(index, len(results)),
                url=_source_url(raw_result),
                published=published,
                freshness=classify_freshness(published),
            )
        )
    return citations
