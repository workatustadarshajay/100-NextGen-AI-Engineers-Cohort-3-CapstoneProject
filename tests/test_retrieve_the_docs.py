from app.services.retrieve_the_docs import retrieve_the_docs


class FakeCollection:
    def __init__(self, result, count=3):
        self._result = result
        self._count = count
        self.query_kwargs = None

    def count(self):
        return self._count

    def query(self, **kwargs):
        self.query_kwargs = kwargs
        return self._result


def _embedding_stub(monkeypatch, recorder=None):
    def fake_embed_texts(texts, task_type, client=None):
        if recorder is not None:
            recorder.append((texts, task_type))
        return [[0.1, 0.2, 0.3]]

    monkeypatch.setattr(
        "app.services.retrieve_the_docs.embed_texts", fake_embed_texts
    )


def test_retrieve_the_docs_maps_chroma_results_to_citations(monkeypatch):
    recorder = []
    _embedding_stub(monkeypatch, recorder)
    collection = FakeCollection(
        {
            "documents": [["Confirm a low haemoglobin result.", "Escalate below 80 g/L."]],
            "metadatas": [
                [
                    {
                        "title": "Anaemia Investigation Pathway",
                        "source": "Neuron Clinical Protocol Library",
                        "section": "Initial assessment",
                    },
                    {
                        "title": "Anaemia Investigation Pathway",
                        "source": "Neuron Clinical Protocol Library",
                        "section": "Escalation",
                    },
                ]
            ],
            "distances": [[0.1, 0.25]],
        }
    )

    citations = retrieve_the_docs("fatigue with low haemoglobin", collection=collection)

    assert [citation.section for citation in citations] == ["Initial assessment", "Escalation"]
    assert citations[0].score == 0.9
    assert citations[1].score == 0.75
    assert citations[0].title == "Anaemia Investigation Pathway"
    assert recorder[0][1] == "RETRIEVAL_QUERY"
    assert recorder[0][0][0].startswith("task: search result | query:")


def test_retrieve_the_docs_limits_results_to_available_chunks(monkeypatch):
    _embedding_stub(monkeypatch)
    collection = FakeCollection(
        {"documents": [[]], "metadatas": [[]], "distances": [[]]}, count=2
    )

    retrieve_the_docs("anything", top_k=8, collection=collection)

    assert collection.query_kwargs["n_results"] == 2


def test_retrieve_the_docs_discards_low_relevance_chunks(monkeypatch):
    _embedding_stub(monkeypatch)
    collection = FakeCollection(
        {
            "documents": [["Useful excerpt", "Weak excerpt"]],
            "metadatas": [[{"title": "Useful"}, {"title": "Weak"}]],
            "distances": [[0.1, 0.95]],
        }
    )

    citations = retrieve_the_docs("haemoglobin", collection=collection)

    assert [citation.title for citation in citations] == ["Useful"]


def test_retrieve_the_docs_returns_no_citations_when_all_matches_are_weak(monkeypatch):
    _embedding_stub(monkeypatch)
    collection = FakeCollection(
        {
            "documents": [["Weak excerpt"]],
            "metadatas": [[{"title": "Weak"}]],
            "distances": [[0.99]],
        }
    )

    assert retrieve_the_docs("haemoglobin", collection=collection) == []


def test_retrieve_the_docs_returns_empty_without_query_or_corpus(monkeypatch):
    _embedding_stub(monkeypatch)
    empty = FakeCollection({"documents": [[]], "metadatas": [[]], "distances": [[]]}, count=0)

    assert retrieve_the_docs("   ", collection=empty) == []
    assert retrieve_the_docs("fatigue", collection=empty) == []
