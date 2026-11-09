import asyncio
import time
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from services import qa
from services.session_memory import session_memory

SID = UUID("00000000-0000-0000-0000-000000000001")


def _doc():
    return Document(
        page_content="RAG combines retrieval with generation.",
        metadata={"doc_id": "d1", "filename": "a.pdf", "page_number": 2},
    )


@pytest.fixture
def store(monkeypatch):
    """Stand-in for the retrieval pipeline (covered separately in test_retrieval.py)."""
    doc = _doc()
    doc.metadata["_score"] = 0.9
    mock = MagicMock(return_value=[doc])
    monkeypatch.setattr(qa, "retrieve_chunks", mock)
    return mock


def _use_llm(monkeypatch, responses):
    llm = FakeListChatModel(responses=responses)
    monkeypatch.setattr(qa, "_get_llm", lambda streaming: llm)


def _collect(**kwargs):
    async def run():
        return [e async for e in qa.astream_answer("What is RAG?", SID, **kwargs)]

    return asyncio.run(run())


def test_get_answer_returns_sources_and_stores_turn(monkeypatch, store):
    _use_llm(monkeypatch, ["RAG is retrieval plus generation."])
    resp = qa.get_answer("What is RAG?", SID, owner_id="alice")

    assert resp.answer == "RAG is retrieval plus generation."
    assert resp.sources[0].filename == "a.pdf"
    assert resp.sources[0].score == pytest.approx(0.9)
    assert store.call_args.kwargs["owner_id"] == "alice"
    assert len(session_memory.get_turns(SID, "alice")) == 1
    assert session_memory.get_turns(SID, "bob") == []


def test_followup_is_condensed_before_retrieval(monkeypatch, store):
    session_memory.add_turn(SID, "earlier q", "earlier a", "alice")
    _use_llm(monkeypatch, ["standalone question", "final answer"])
    qa.get_answer("and why?", SID, owner_id="alice")
    assert store.call_args.args[0] == "standalone question"


def test_stream_event_order_and_memory(monkeypatch, store):
    _use_llm(monkeypatch, ["Hello"])
    events = _collect(owner_id="alice")
    types = [e["type"] for e in events]
    assert types[-1] == "done" and types[-2] == "sources"
    assert "".join(e["data"] for e in events if e["type"] == "token") == "Hello"
    assert session_memory.get_turns(SID, "alice")[0]["answer"] == "Hello"


def test_stream_retrieval_failure_emits_error_without_leaking(monkeypatch, store):
    _use_llm(monkeypatch, ["x"])
    store.side_effect = RuntimeError("chroma secret path /data/x")
    events = _collect(owner_id="alice")
    assert [e["type"] for e in events] == ["error"]
    assert "secret" not in events[0]["data"]
    assert session_memory.get_turns(SID, "alice") == []


def test_stream_does_not_block_event_loop(monkeypatch, store):
    """A slow retrieval must not freeze other coroutines on the same loop."""
    _use_llm(monkeypatch, ["ok"])
    store.side_effect = lambda *a, **k: (time.sleep(0.4), [_doc()])[1]

    async def run():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1

        t = asyncio.create_task(ticker())
        [e async for e in qa.astream_answer("q", SID, owner_id="alice")]
        t.cancel()
        return ticks

    # A blocked loop would record ~0 ticks during the 0.4s retrieval.
    assert asyncio.run(run()) >= 10
