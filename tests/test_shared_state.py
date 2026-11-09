import asyncio
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import fakeredis
import pytest
from arq import Retry
from fastapi import BackgroundTasks
from langchain_core.documents import Document

from core.config import get_settings
from services.document_registry import (
    InMemoryDocumentRegistry,
    SqlDocumentRegistry,
    _LazyRegistry,
)
from services.session_memory import InMemorySessionMemory, RedisSessionMemory, _LazySessionMemory

SID = UUID("00000000-0000-0000-0000-000000000001")


# ── SQL document registry (SQLite stands in for Postgres) ───────────────────

@pytest.fixture
def sql_registry():
    return SqlDocumentRegistry("sqlite://")


def test_sql_registry_lifecycle(sql_registry):
    d = uuid4()
    entry = sql_registry.register(d, "a.pdf", "alice")
    assert entry.status == "processing"

    sql_registry.mark_ready(d, 7)
    got = sql_registry.get(d, "alice")
    assert got.status == "ready" and got.chunk_count == 7 and got.owner_id == "alice"
    assert got.created_at.tzinfo is not None

    sql_registry.mark_failed(d, "boom")
    assert sql_registry.get(d, "alice").error == "boom"

    assert sql_registry.delete(d, "alice") is True
    assert sql_registry.get(d, "alice") is None


def test_sql_registry_isolates_owners(sql_registry):
    d = uuid4()
    sql_registry.register(d, "a.pdf", "alice")
    assert sql_registry.get(d, "bob") is None
    assert sql_registry.list_all("bob") == []
    assert sql_registry.delete(d, "bob") is False
    assert sql_registry.count("alice") == 1 and sql_registry.count("bob") == 0
    assert len(sql_registry.list_all("alice")) == 1


@pytest.mark.parametrize("make", [lambda: SqlDocumentRegistry("sqlite://"), InMemoryDocumentRegistry])
def test_fail_stale_only_hits_old_processing_docs(make):
    reg = make()
    old, fresh, done = uuid4(), uuid4(), uuid4()
    for d in (old, fresh, done):
        reg.register(d, "x.pdf", "alice")
    reg.mark_ready(done, 1)

    # Age the 'old' doc by backdating its creation time.
    if isinstance(reg, InMemoryDocumentRegistry):
        reg._store[str(old)] = reg._store[str(old)].model_copy(
            update={"created_at": datetime.now(UTC) - timedelta(hours=2)}
        )
    else:
        from sqlalchemy import update

        from services.document_registry import _documents

        with reg._engine.begin() as conn:
            conn.execute(
                update(_documents)
                .where(_documents.c.doc_id == str(old))
                .values(created_at=datetime.now(UTC) - timedelta(hours=2))
            )

    assert reg.fail_stale(30) == 1
    assert reg.get(old, "alice").status == "failed"
    assert reg.get(fresh, "alice").status == "processing"
    assert reg.get(done, "alice").status == "ready"


def test_lazy_registry_picks_backend_from_settings(monkeypatch):
    monkeypatch.setattr(get_settings(), "DATABASE_URL", "sqlite://")
    assert isinstance(_LazyRegistry()._resolve(), SqlDocumentRegistry)
    monkeypatch.setattr(get_settings(), "DATABASE_URL", "")
    assert isinstance(_LazyRegistry()._resolve(), InMemoryDocumentRegistry)


# ── Redis session memory (fakeredis) ────────────────────────────────────────

@pytest.fixture
def redis_mem():
    client = fakeredis.FakeRedis(decode_responses=True)
    return RedisSessionMemory(client), client


def test_redis_memory_trims_to_max_turns_and_sets_ttl(redis_mem, monkeypatch):
    mem, client = redis_mem
    monkeypatch.setattr(get_settings(), "MAX_CONVERSATION_TURNS", 3)
    for i in range(5):
        mem.add_turn(SID, f"Q{i}", f"A{i}", "alice")
    turns = mem.get_turns(SID, "alice")
    assert [t["question"] for t in turns] == ["Q2", "Q3", "Q4"]
    assert 0 < client.ttl(f"session:alice:{SID}") <= get_settings().SESSION_TTL_SECONDS


def test_redis_memory_namespaced_and_clearable(redis_mem):
    mem, _ = redis_mem
    mem.add_turn(SID, "q", "a", "alice")
    assert mem.get_turns(SID, "bob") == []
    mem.clear(SID, "alice")
    assert mem.get_turns(SID, "alice") == []


def test_lazy_session_memory_picks_backend(monkeypatch):
    monkeypatch.setattr(get_settings(), "REDIS_URL", "")
    assert isinstance(_LazySessionMemory()._resolve(), InMemorySessionMemory)
    monkeypatch.setattr(get_settings(), "REDIS_URL", "redis://localhost:6379/0")
    assert isinstance(_LazySessionMemory()._resolve(), RedisSessionMemory)  # connects lazily


# ── job queue ───────────────────────────────────────────────────────────────

def test_enqueue_falls_back_to_background_task_without_redis(monkeypatch):
    from services import job_queue

    monkeypatch.setattr(get_settings(), "REDIS_URL", "")
    bt = BackgroundTasks()
    asyncio.run(job_queue.enqueue_ingestion(bt, uuid4(), Path("f.pdf"), ".pdf", "f.pdf", "alice"))
    assert len(bt.tasks) == 1


def test_enqueue_uses_arq_with_idempotent_job_id(monkeypatch):
    from services import job_queue

    monkeypatch.setattr(get_settings(), "REDIS_URL", "redis://x:6379/0")
    pool = MagicMock(enqueue_job=AsyncMock())
    monkeypatch.setattr(job_queue, "_get_pool", AsyncMock(return_value=pool))
    d = uuid4()
    bt = BackgroundTasks()
    asyncio.run(job_queue.enqueue_ingestion(bt, d, Path("f.pdf"), ".pdf", "f.pdf", "alice"))

    assert bt.tasks == []
    args, kwargs = pool.enqueue_job.call_args
    assert args[0] == "ingest_job" and args[1] == str(d) and args[-1] == "alice"
    assert kwargs["_job_id"] == str(d)


def test_upload_returns_503_and_rolls_back_when_queue_down(client):
    from services.document_registry import document_registry

    with patch("api.routes.enqueue_ingestion", new=AsyncMock(side_effect=ConnectionError("redis down"))):
        r = client.post(
            "/upload", files={"file": ("a.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")}
        )
    assert r.status_code == 503
    assert document_registry.list_all("alice") == []


# ── ingestion + worker ──────────────────────────────────────────────────────

def test_run_ingestion_tags_owner_and_clears_partial_chunks(monkeypatch):
    from services import ingestion

    calls = []
    store = MagicMock()
    store.delete_document.side_effect = lambda d: calls.append("delete")
    store.store_chunks.side_effect = lambda c: calls.append("store")
    reg = MagicMock()
    chunks = [Document(page_content="x", metadata={})]
    monkeypatch.setattr(ingestion, "vector_store_manager", store)
    monkeypatch.setattr(ingestion, "document_registry", reg)
    monkeypatch.setattr(ingestion, "extract_text", lambda p, t: ["raw"])
    monkeypatch.setattr(ingestion, "chunk_documents", lambda docs, d, f: chunks)

    d = uuid4()
    assert ingestion.run_ingestion(d, Path("f.pdf"), ".pdf", "f.pdf", "alice") == 1
    assert chunks[0].metadata["owner_id"] == "alice"
    assert calls == ["delete", "store"]
    reg.mark_ready.assert_called_once_with(d, 1)


def test_ingest_document_marks_failed_on_error(monkeypatch):
    from services import ingestion

    reg = MagicMock()
    monkeypatch.setattr(ingestion, "document_registry", reg)
    monkeypatch.setattr(ingestion, "run_ingestion", MagicMock(side_effect=RuntimeError("secret detail")))
    d = uuid4()
    ingestion.ingest_document(d, Path("f.pdf"), ".pdf", "f.pdf", "alice")
    reg.mark_failed.assert_called_once_with(d, ingestion.GENERIC_FAILURE)


def test_worker_retries_then_marks_failed(monkeypatch):
    import worker

    reg = MagicMock()
    monkeypatch.setattr(worker, "document_registry", reg)
    monkeypatch.setattr(worker, "run_ingestion", MagicMock(side_effect=RuntimeError("boom")))
    d = str(uuid4())

    with pytest.raises(Retry):
        asyncio.run(worker.ingest_job({"job_try": 1}, d, "f.pdf", ".pdf", "f.pdf", "alice"))
    reg.mark_failed.assert_not_called()

    last = worker._settings.INGEST_MAX_TRIES
    asyncio.run(worker.ingest_job({"job_try": last}, d, "f.pdf", ".pdf", "f.pdf", "alice"))
    reg.mark_failed.assert_called_once()
    assert "boom" not in reg.mark_failed.call_args.args[1]


def test_worker_success_does_not_mark_failed(monkeypatch):
    import worker

    reg = MagicMock()
    monkeypatch.setattr(worker, "document_registry", reg)
    monkeypatch.setattr(worker, "run_ingestion", MagicMock(return_value=3))
    asyncio.run(worker.ingest_job({"job_try": 1}, str(uuid4()), "f.pdf", ".pdf", "f.pdf", "alice"))
    reg.mark_failed.assert_not_called()
