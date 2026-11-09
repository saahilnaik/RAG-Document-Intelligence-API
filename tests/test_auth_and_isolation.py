import io

PDF = ("a.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")
SESSION = "00000000-0000-0000-0000-000000000001"


def _upload(c, name="a.pdf", data=b"%PDF-1.4 fake"):
    return c.post("/upload", files={"file": (name, io.BytesIO(data), "application/pdf")})


# ── auth ────────────────────────────────────────────────────────────────────

def test_health_is_public(anon_client):
    assert anon_client.get("/health").status_code == 200


def test_missing_key_rejected(anon_client):
    assert anon_client.get("/documents").status_code == 401
    assert _upload(anon_client).status_code == 401
    assert anon_client.post("/evaluate", json={
        "question": "q", "answer": "a", "contexts": [],
    }).status_code == 401


def test_invalid_key_rejected(anon_client):
    r = anon_client.get("/documents", headers={"X-API-Key": "nope"})
    assert r.status_code == 401


# ── tenant isolation ────────────────────────────────────────────────────────

def test_users_cannot_see_each_others_documents(client, bob_client):
    doc_id = _upload(client).json()["doc_id"]
    assert bob_client.get("/documents").json() == []
    assert bob_client.get(f"/documents/{doc_id}").status_code == 404
    assert len(client.get("/documents").json()) == 1


def test_user_cannot_delete_others_document(client, bob_client):
    doc_id = _upload(client).json()["doc_id"]
    assert bob_client.delete(f"/documents/{doc_id}").status_code == 404
    assert client.get(f"/documents/{doc_id}").status_code == 200


def test_user_cannot_ask_about_others_document(client, bob_client):
    doc_id = _upload(client).json()["doc_id"]
    r = bob_client.post("/ask", json={"question": "hi", "session_id": SESSION, "doc_id": doc_id})
    assert r.status_code == 404


def test_owner_id_not_leaked(client):
    _upload(client)
    assert "owner_id" not in client.get("/documents").json()[0]


def test_session_memory_namespaced_by_owner():
    from uuid import UUID

    from services.session_memory import session_memory

    sid = UUID(SESSION)
    session_memory.add_turn(sid, "q", "a", owner_id="alice")
    assert session_memory.get_turns(sid, "bob") == []
    assert len(session_memory.get_turns(sid, "alice")) == 1


def test_retrieve_filters_by_owner(monkeypatch):
    from unittest.mock import MagicMock

    from services.vector_store import VectorStoreManager

    mgr = VectorStoreManager()
    store = MagicMock()
    store._embedding_function.embed_query.return_value = [0.0]
    store._collection.query.return_value = {"ids": [[]], "documents": [[]]}
    mgr._store = store

    mgr.retrieve("q", k=3, owner_id="alice")
    assert store._collection.query.call_args.kwargs["where"] == {"owner_id": "alice"}
    mgr.retrieve("q", k=3, doc_id="d1", owner_id="alice")
    assert store._collection.query.call_args.kwargs["where"] == {
        "$and": [{"owner_id": "alice"}, {"doc_id": "d1"}]
    }


# ── upload hardening ────────────────────────────────────────────────────────

def test_upload_content_mismatch_rejected(client):
    assert _upload(client, "fake.pdf", b"MZ\x90\x00 not a pdf").status_code == 415


def test_upload_empty_rejected(client):
    assert _upload(client, "empty.pdf", b"").status_code == 400


def test_upload_filename_sanitized(client):
    r = _upload(client, "../../etc/evil.pdf")
    assert r.status_code == 202
    assert r.json()["filename"] == "evil.pdf"


def test_upload_document_cap(client, monkeypatch):
    from core.config import get_settings

    monkeypatch.setattr(get_settings(), "MAX_DOCS_PER_USER", 1)
    assert _upload(client).status_code == 202
    assert _upload(client).status_code == 429


# ── input limits ────────────────────────────────────────────────────────────

def test_question_too_long_rejected(client):
    r = client.post("/ask", json={"question": "x" * 2001, "session_id": SESSION})
    assert r.status_code == 422


def test_empty_question_rejected(client):
    assert client.post("/ask", json={"question": "", "session_id": SESSION}).status_code == 422
