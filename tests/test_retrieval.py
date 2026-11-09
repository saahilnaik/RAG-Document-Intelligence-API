import asyncio
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from core.config import get_settings
from services import qa, retrieval
from services.bm25 import BM25Index, tokenize
from services.citations import find_unverified_citations
from services.eval_gate import failures, mean_scores, parse_thresholds
from services.session_memory import session_memory
from services.vector_store import VectorStoreManager

SID = UUID("00000000-0000-0000-0000-000000000001")


def D(cid, text="text", **meta):
    return Document(page_content=text, metadata={"_chunk_id": cid, "filename": "a.pdf", "page_number": 1, **meta})


# ── BM25 ────────────────────────────────────────────────────────────────────

def test_tokenize_lowercases_and_drops_stopwords():
    assert tokenize("The Quick-Brown fox, 42!") == ["quick", "brown", "fox", "42"]


def test_bm25_ranks_exact_term_match_first():
    idx = BM25Index(["general notes about weather", "invoice INV-2041 total due", "unrelated cooking recipe"])
    hits = idx.top_k("INV-2041", 3)
    assert hits[0][0] == 1 and len(hits) == 1  # only the doc containing the term scores


def test_bm25_empty_and_unknown_queries():
    assert BM25Index([]).top_k("x", 3) == []
    assert BM25Index(["alpha beta"]).top_k("zzz", 3) == []


def test_bm25_prefers_rarer_terms():
    idx = BM25Index(["common common common rare", "common common common common"])
    assert idx.top_k("common rare", 2)[0][0] == 0


# ── RRF fusion ──────────────────────────────────────────────────────────────

def test_rrf_rewards_agreement_between_retrievers():
    a, b, c = D("a"), D("b"), D("c")
    fused = retrieval.rrf_fuse([[a, b, c], [c, b]])
    assert [d.metadata["_chunk_id"] for d in fused] == ["c", "b", "a"]  # b and c appear in both lists; c edges b (rank 1 in one list)


def test_rrf_dedupes():
    fused = retrieval.rrf_fuse([[D("a")], [D("a")]])
    assert len(fused) == 1


# ── retrieve_chunks pipeline ────────────────────────────────────────────────

@pytest.fixture
def pipeline(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "HYBRID_ENABLED", True)
    monkeypatch.setattr(s, "RERANK_ENABLED", True)
    monkeypatch.setattr(s, "MIN_RELEVANCE_SCORE", 0.01)
    store, rr = MagicMock(), MagicMock()
    store.retrieve.return_value = [(D("a"), 0.8), (D("b"), 0.7)]
    store.keyword_search.return_value = [(D("c"), 5.0), (D("a"), 3.0)]
    monkeypatch.setattr(retrieval, "vector_store_manager", store)
    monkeypatch.setattr(retrieval, "reranker", rr)
    return store, rr


def test_pipeline_reranks_and_orders_by_rerank_score(pipeline):
    _, rr = pipeline
    # shortlist after fusion is [a, c, b]; reranker says c best, then b, a lowest
    rr.score.side_effect = lambda q, texts: [0.2, 0.9, 0.5]
    out = retrieval.retrieve_chunks("q", k=3, owner_id="alice")
    assert [d.metadata["_chunk_id"] for d in out] == ["c", "b", "a"]
    assert out[0].metadata["_score"] == 0.9


def test_pipeline_drops_chunks_below_threshold(pipeline):
    _, rr = pipeline
    rr.score.side_effect = lambda q, texts: [0.9, 0.0001, 0.5]
    out = retrieval.retrieve_chunks("q", k=5)
    assert [d.metadata["_chunk_id"] for d in out] == ["a", "b"]


def test_pipeline_returns_empty_when_nothing_relevant(pipeline):
    _, rr = pipeline
    rr.score.side_effect = lambda q, texts: [0.0001] * len(texts)
    assert retrieval.retrieve_chunks("q", k=5) == []


def test_pipeline_respects_k(pipeline):
    _, rr = pipeline
    rr.score.side_effect = lambda q, texts: [0.9, 0.8, 0.7]
    assert len(retrieval.retrieve_chunks("q", k=2)) == 2


def test_pipeline_passes_scope_filters(pipeline):
    store, rr = pipeline
    rr.score.return_value = [0.9, 0.9, 0.9]
    retrieval.retrieve_chunks("q", k=3, doc_id="d1", owner_id="alice")
    for call in (store.retrieve.call_args, store.keyword_search.call_args):
        assert call.kwargs["doc_id"] == "d1" and call.kwargs["owner_id"] == "alice"


def test_pipeline_falls_back_to_similarity_when_reranker_unavailable(pipeline, monkeypatch):
    _, rr = pipeline
    rr.score.return_value = None  # model failed to load
    monkeypatch.setattr(get_settings(), "MIN_RELEVANCE_SCORE", 0.75)
    out = retrieval.retrieve_chunks("q", k=5)
    ids = [d.metadata["_chunk_id"] for d in out]
    # a (sim .8) kept; b (sim .7) dropped; c is keyword-only (no similarity) so kept
    assert ids == ["a", "c"]


def test_pipeline_hybrid_off_skips_keyword_search(pipeline, monkeypatch):
    store, rr = pipeline
    monkeypatch.setattr(get_settings(), "HYBRID_ENABLED", False)
    rr.score.side_effect = lambda q, texts: [0.9] * len(texts)
    out = retrieval.retrieve_chunks("q", k=5)
    store.keyword_search.assert_not_called()
    assert {d.metadata["_chunk_id"] for d in out} == {"a", "b"}


def test_pipeline_rerank_off_does_not_load_reranker(pipeline, monkeypatch):
    _, rr = pipeline
    monkeypatch.setattr(get_settings(), "RERANK_ENABLED", False)
    monkeypatch.setattr(get_settings(), "MIN_RELEVANCE_SCORE", 0.0)
    retrieval.retrieve_chunks("q", k=5)
    rr.score.assert_not_called()


# ── keyword search over Chroma (fake collection) ────────────────────────────

class FakeCollection:
    def __init__(self, rows):
        self.rows = rows  # id -> (text, meta)
        self.full_reads = 0

    def get(self, where=None, include=None):
        ids = list(self.rows)
        if include == []:
            return {"ids": ids}
        self.full_reads += 1
        return {
            "ids": ids,
            "documents": [self.rows[i][0] for i in ids],
            "metadatas": [self.rows[i][1] for i in ids],
        }


def _manager(rows):
    mgr = VectorStoreManager()
    mgr._store = MagicMock()
    mgr._store._collection = FakeCollection(rows)
    return mgr, mgr._store._collection


def test_keyword_search_finds_exact_term_and_tags_chunk_id():
    mgr, _ = _manager({"c1": ("totally unrelated prose", {}), "c2": ("order ZX-9000 shipped", {"filename": "f.pdf"})})
    hits = mgr.keyword_search("ZX-9000", k=3, owner_id="alice")
    assert [d.metadata["_chunk_id"] for d, _ in hits] == ["c2"]
    assert hits[0][0].metadata["filename"] == "f.pdf"


def test_keyword_index_cached_until_chunk_set_changes():
    mgr, coll = _manager({"c1": ("alpha beta", {})})
    mgr.keyword_search("alpha", k=3, owner_id="alice")
    mgr.keyword_search("beta", k=3, owner_id="alice")
    assert coll.full_reads == 1  # second call reused the index
    coll.rows["c2"] = ("gamma delta", {})  # e.g. the worker ingested more
    assert mgr.keyword_search("gamma", k=3, owner_id="alice")[0][0].metadata["_chunk_id"] == "c2"
    assert coll.full_reads == 2


def test_keyword_index_scoped_per_owner():
    mgr, coll = _manager({"c1": ("alpha", {})})
    mgr.keyword_search("alpha", k=1, owner_id="alice")
    mgr.keyword_search("alpha", k=1, owner_id="bob")
    assert coll.full_reads == 2


def test_keyword_search_skipped_for_oversized_scope(monkeypatch):
    monkeypatch.setattr(get_settings(), "HYBRID_MAX_CHUNKS", 1)
    mgr, coll = _manager({"c1": ("alpha", {}), "c2": ("alpha", {})})
    assert mgr.keyword_search("alpha", k=3, owner_id="alice") == []
    assert coll.full_reads == 0


# ── citations ───────────────────────────────────────────────────────────────

DOCS = [Document(page_content="x", metadata={"filename": "Report.pdf", "page_number": 3})]


def test_valid_citation_passes():
    assert find_unverified_citations("It grew [Report.pdf:3].", DOCS) == []


def test_wrong_page_is_flagged():
    assert find_unverified_citations("See [Report.pdf:9].", DOCS) == ["[Report.pdf:9]"]


def test_unknown_file_is_flagged():
    assert find_unverified_citations("See [Made-Up.pdf:1].", DOCS) == ["[Made-Up.pdf:1]"]


def test_prose_in_brackets_is_not_a_citation():
    assert find_unverified_citations("Note [see: below] and [x: y].", DOCS) == []


def test_case_insensitive_filename_and_dedupe():
    ans = "[report.PDF:3] ok, but [Ghost.docx:1] and again [Ghost.docx:1]"
    assert find_unverified_citations(ans, DOCS) == ["[Ghost.docx:1]"]


# ── qa: no-answer + unverified citations + LLM fallback ─────────────────────

def _use_llm(monkeypatch, responses):
    llm = FakeListChatModel(responses=responses)
    monkeypatch.setattr(qa, "_get_llm", lambda streaming: llm)
    return llm


def test_get_answer_short_circuits_when_nothing_relevant(monkeypatch):
    monkeypatch.setattr(qa, "retrieve_chunks", MagicMock(return_value=[]))
    llm = _use_llm(monkeypatch, ["SHOULD NOT BE USED"])
    resp = qa.get_answer("anything?", SID, owner_id="alice")
    assert resp.answer == qa.NO_ANSWER_TEXT and resp.sources == []
    assert llm.i == 0  # the model was never called
    assert session_memory.get_turns(SID, "alice")[0]["answer"] == qa.NO_ANSWER_TEXT


def test_stream_short_circuits_when_nothing_relevant(monkeypatch):
    monkeypatch.setattr(qa, "retrieve_chunks", MagicMock(return_value=[]))
    llm = _use_llm(monkeypatch, ["SHOULD NOT BE USED"])

    async def run():
        return [e async for e in qa.astream_answer("anything?", SID, owner_id="alice")]

    events = asyncio.run(run())
    assert [e["type"] for e in events] == ["token", "sources", "done"]
    assert events[0]["data"] == qa.NO_ANSWER_TEXT and events[1]["data"] == []
    assert llm.i == 0


def _doc_with_score():
    d = Document(page_content="Facts.", metadata={"doc_id": "d1", "filename": "a.pdf", "page_number": 2, "_score": 0.9})
    return d


def test_get_answer_reports_unverified_citations(monkeypatch):
    monkeypatch.setattr(qa, "retrieve_chunks", MagicMock(return_value=[_doc_with_score()]))
    _use_llm(monkeypatch, ["True [a.pdf:2] but also [fake.pdf:7]."])
    resp = qa.get_answer("q", SID, owner_id="alice")
    assert resp.unverified_citations == ["[fake.pdf:7]"]


def test_stream_emits_citations_event_before_sources(monkeypatch):
    monkeypatch.setattr(qa, "retrieve_chunks", MagicMock(return_value=[_doc_with_score()]))
    _use_llm(monkeypatch, ["Claim [fake.pdf:7]."])

    async def run():
        return [e async for e in qa.astream_answer("q", SID, owner_id="alice")]

    events = asyncio.run(run())
    types = [e["type"] for e in events]
    assert types[-3:] == ["citations", "sources", "done"]
    assert [e for e in events if e["type"] == "citations"][0]["data"] == {"unverified": ["[fake.pdf:7]"]}


def test_llm_has_fallback_model_when_configured(monkeypatch):
    built = []
    fake = MagicMock()
    fake.with_fallbacks.side_effect = lambda fbs: ("with_fallbacks", fbs)
    monkeypatch.setattr(qa, "_build_llm", lambda model, streaming: (built.append(model), fake)[1])
    monkeypatch.setattr(get_settings(), "GROQ_FALLBACK_MODEL", "small-model")
    qa._get_llm.cache_clear()
    try:
        result = qa._get_llm(False)
    finally:
        qa._get_llm.cache_clear()
    assert built == [get_settings().GROQ_CHAT_MODEL, "small-model"]
    assert result[0] == "with_fallbacks"


def test_llm_has_no_fallback_when_disabled(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(qa, "_build_llm", lambda model, streaming: fake)
    monkeypatch.setattr(get_settings(), "GROQ_FALLBACK_MODEL", "")
    qa._get_llm.cache_clear()
    try:
        assert qa._get_llm(True) is fake
    finally:
        qa._get_llm.cache_clear()


# ── eval gate ───────────────────────────────────────────────────────────────

def test_parse_thresholds():
    assert parse_thresholds(["faithfulness=0.7", "answer_relevancy=0.5"]) == {
        "faithfulness": 0.7, "answer_relevancy": 0.5,
    }
    with pytest.raises(ValueError):
        parse_thresholds(["bogus=1"])
    with pytest.raises(ValueError):
        parse_thresholds(["faithfulness"])


def test_gate_passes_and_fails_on_means():
    rows = [{"faithfulness": 0.9}, {"faithfulness": 0.5}]
    assert mean_scores(rows)["faithfulness"] == pytest.approx(0.7)
    assert failures(rows, {"faithfulness": 0.7}) == []
    assert "faithfulness" in failures(rows, {"faithfulness": 0.8})[0]


def test_gate_ignores_nan_and_fails_when_no_scores():
    nan = float("nan")
    assert mean_scores([{"faithfulness": nan}, {"faithfulness": 0.8}])["faithfulness"] == pytest.approx(0.8)
    assert "no scores" in failures([{"faithfulness": nan}, {"faithfulness": None}], {"faithfulness": 0.5})[0]
