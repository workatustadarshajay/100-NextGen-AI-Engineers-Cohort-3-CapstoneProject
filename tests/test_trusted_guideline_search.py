import json
from types import SimpleNamespace

from app.services import retrieve_the_docs as retrieve_module
from app.services.ai.schemas import GuidelineCitation
from app.services.trusted_guideline_search import (
    classify_freshness,
    search_trusted_guidelines,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, limit):
        return self.payload


def test_classify_freshness_labels_age_without_deciding_validity():
    from datetime import date

    assert classify_freshness("2025-01-01", today=date(2026, 9, 18)) == "current"
    assert classify_freshness("2022-01-01", today=date(2026, 9, 18)) == "aging"
    assert classify_freshness("2018-01-01", today=date(2026, 9, 18)) == "old"
    assert classify_freshness("not-a-date", today=date(2026, 9, 18)) == "unknown"


def test_search_trusted_guidelines_maps_sanitized_source_metadata():
    requests = []
    payload = {
        "resultList": {
            "result": [
                {
                    "title": "Practice guideline for anaemia",
                    "abstractText": "<p>Assess haemoglobin and investigate iron deficiency.</p>",
                    "firstPublicationDate": "2026-01-15",
                    "journalTitle": "Clinical Medicine",
                    "pmid": "12345678",
                }
            ]
        }
    }

    def opener(request, timeout):
        requests.append((request, timeout))
        return FakeResponse(payload)

    citations = search_trusted_guidelines(
        "fatigue and low haemoglobin",
        limit=3,
        timeout=4,
        opener=opener,
    )

    assert len(citations) == 1
    assert citations[0] == GuidelineCitation(
        title="Practice guideline for anaemia",
        source="Europe PMC / PubMed",
        section="Clinical Medicine",
        excerpt="Assess haemoglobin and investigate iron deficiency.",
        score=1.0,
        url="https://europepmc.org/article/MED/12345678",
        published="2026-01-15",
        freshness="current",
    )
    assert requests[0][0].full_url.startswith(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
    )
    assert "guideline" in requests[0][0].full_url
    assert requests[0][1] == 4


def test_retrieval_uses_trusted_search_when_local_corpus_is_empty(monkeypatch):
    settings = SimpleNamespace(
        trusted_search_enabled=True,
        trusted_search_limit=2,
        top_k=4,
        min_relevance_score=0.2,
    )
    searched = []

    def trusted_search(query, *, limit):
        searched.append((query, limit))
        return [
            GuidelineCitation(
                title="Trusted result",
                source="Europe PMC / PubMed",
                excerpt="Evidence excerpt",
                url="https://europepmc.org/article/MED/1",
            )
        ]

    monkeypatch.setattr(retrieve_module, "get_ai_settings", lambda: settings)
    citations = retrieve_module.retrieve_the_docs(
        "fatigue with low haemoglobin",
        collection=SimpleNamespace(count=lambda: 0),
        trusted_search=trusted_search,
    )

    assert citations[0].title == "Trusted result"
    assert searched == [("fatigue with low haemoglobin", 2)]


def test_retrieval_does_not_call_trusted_search_when_local_match_exists(monkeypatch):
    settings = SimpleNamespace(
        trusted_search_enabled=True,
        trusted_search_limit=2,
        top_k=4,
        min_relevance_score=0.2,
    )
    local_collection = SimpleNamespace(
        count=lambda: 1,
        query=lambda **kwargs: {
            "documents": [["Local guideline excerpt"]],
            "metadatas": [[{"title": "Local guideline", "source": "Local library"}]],
            "distances": [[0.1]],
        },
    )
    monkeypatch.setattr(retrieve_module, "get_ai_settings", lambda: settings)
    monkeypatch.setattr(
        retrieve_module,
        "embed_texts",
        lambda *args, **kwargs: [[0.1, 0.2]],
    )

    def trusted_search(*args, **kwargs):
        raise AssertionError("trusted search should not run for a local hit")

    citations = retrieve_module.retrieve_the_docs(
        "fatigue",
        collection=local_collection,
        trusted_search=trusted_search,
    )

    assert citations[0].title == "Local guideline"
