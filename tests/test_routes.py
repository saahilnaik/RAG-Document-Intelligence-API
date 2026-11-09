import io
import json
from uuid import UUID, uuid4

import pytest


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_upload_valid_pdf(client):
    resp = client.post(
        "/upload",
        files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["filename"] == "test.pdf"
    assert body["status"] == "processing"
    assert "doc_id" in body


def test_upload_invalid_extension(client):
    resp = client.post(
        "/upload",
        files={"file": ("malware.exe", io.BytesIO(b"data"), "application/octet-stream")},
    )
    assert resp.status_code == 415


def test_upload_too_large(client):
    large = b"x" * (26 * 1024 * 1024)  # 26 MB > 25 MB limit
    resp = client.post(
        "/upload",
        files={"file": ("big.pdf", io.BytesIO(large), "application/pdf")},
    )
    assert resp.status_code == 413


def test_list_documents_empty(client):
    resp = client.get("/documents")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_documents_after_upload(client):
    client.post(
        "/upload",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    resp = client.get("/documents")
    docs = resp.json()
    assert len(docs) == 1
    assert docs[0]["filename"] == "doc.pdf"
    assert docs[0]["status"] == "processing"  # _ingest_document is mocked, stays processing


def test_get_document_not_found(client):
    assert client.get(f"/documents/{uuid4()}").status_code == 404


def test_get_document_after_upload(client):
    upload = client.post(
        "/upload",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    doc_id = upload.json()["doc_id"]
    resp = client.get(f"/documents/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["doc_id"] == doc_id


def test_delete_document_not_found(client):
    assert client.delete(f"/documents/{uuid4()}").status_code == 404


def test_delete_document_success(client):
    upload = client.post(
        "/upload",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    doc_id = upload.json()["doc_id"]
    assert client.delete(f"/documents/{doc_id}").status_code == 204
    assert client.get(f"/documents/{doc_id}").status_code == 404


# ── /ask ────────────────────────────────────────────────────────────────────

def test_ask_success(client):
    from services.document_registry import document_registry as reg

    upload = client.post(
        "/upload",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    doc_id = upload.json()["doc_id"]
    reg.mark_ready(UUID(doc_id), chunk_count=3)

    resp = client.post("/ask", json={
        "question": "What is this about?",
        "session_id": "00000000-0000-0000-0000-000000000001",
        "doc_id": doc_id,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Canned answer"
    assert body["sources"] == []
    assert "session_id" in body


def test_ask_processing_doc_returns_409(client):
    upload = client.post(
        "/upload",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    doc_id = upload.json()["doc_id"]
    resp = client.post("/ask", json={
        "question": "What is this?",
        "session_id": "00000000-0000-0000-0000-000000000001",
        "doc_id": doc_id,
    })
    assert resp.status_code == 409


def test_ask_unknown_doc_returns_404(client):
    resp = client.post("/ask", json={
        "question": "What is this?",
        "session_id": "00000000-0000-0000-0000-000000000001",
        "doc_id": str(uuid4()),
    })
    assert resp.status_code == 404


def test_ask_no_doc_id_global_retrieval(client):
    resp = client.post("/ask", json={
        "question": "What is this about?",
        "session_id": "00000000-0000-0000-0000-000000000001",
    })
    assert resp.status_code == 200
    assert resp.json()["answer"] == "Canned answer"


# ── /ask/stream ──────────────────────────────────────────────────────────────

def test_ask_stream_yields_sse_events(client):
    with client.stream("POST", "/ask/stream", json={
        "question": "What is this about?",
        "session_id": "00000000-0000-0000-0000-000000000001",
    }) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        raw = resp.read().decode()
    lines = raw.strip().split("\n\n")
    events = [json.loads(line.removeprefix("data: ")) for line in lines if line.startswith("data: ")]

    types = [e["type"] for e in events]
    assert "token" in types
    assert "sources" in types
    assert types[-1] == "done"
    tokens = [e["data"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == "Canned answer"


def test_ask_stream_processing_doc_returns_409(client):
    upload = client.post(
        "/upload",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    doc_id = upload.json()["doc_id"]
    resp = client.post("/ask/stream", json={
        "question": "What is this?",
        "session_id": "00000000-0000-0000-0000-000000000001",
        "doc_id": doc_id,
    })
    assert resp.status_code == 409


def test_ask_stream_unknown_doc_returns_404(client):
    resp = client.post("/ask/stream", json={
        "question": "What is this?",
        "session_id": "00000000-0000-0000-0000-000000000001",
        "doc_id": str(uuid4()),
    })
    assert resp.status_code == 404


# ── /evaluate ────────────────────────────────────────────────────────────────

def test_evaluate_returns_scores(client):
    resp = client.post("/evaluate", json={
        "question": "What is RAG?",
        "answer": "RAG is Retrieval-Augmented Generation.",
        "contexts": ["RAG combines retrieval with generation."],
        "ground_truth": "RAG stands for Retrieval-Augmented Generation.",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["faithfulness"] == pytest.approx(0.9)
    assert body["answer_relevancy"] == pytest.approx(0.85)
    assert body["context_precision"] == pytest.approx(0.8)


def test_evaluate_without_ground_truth(client):
    resp = client.post("/evaluate", json={
        "question": "What is RAG?",
        "answer": "RAG is Retrieval-Augmented Generation.",
        "contexts": ["RAG combines retrieval with generation."],
    })
    assert resp.status_code == 200
