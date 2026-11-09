import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_tmp = tempfile.gettempdir()

# Set dummy env vars before any app imports so Settings validation passes
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("CHROMA_PERSIST_DIR", f"{_tmp}/test-chroma")
os.environ.setdefault("UPLOAD_DIR", f"{_tmp}/test-uploads")
# Force in-process backends regardless of any local .env
os.environ["DATABASE_URL"] = ""
os.environ["REDIS_URL"] = ""
os.environ["CHROMA_HOST"] = ""
os.environ["AUTH_ENABLED"] = "true"
os.environ["API_KEYS"] = '{"test-key-alice": "alice", "test-key-bob": "bob"}'


@pytest.fixture(autouse=True)
def _reset_registries():
    from services.document_registry import document_registry
    from services.session_memory import session_memory

    document_registry._store.clear()
    session_memory._sessions.clear()
    yield
    document_registry._store.clear()
    session_memory._sessions.clear()


@pytest.fixture
def mock_vector_store():
    mock = MagicMock()
    with (
        patch("services.vector_store.vector_store_manager", mock),
        patch("api.routes.vector_store_manager", mock),
        patch("api.routes.enqueue_ingestion", new_callable=AsyncMock),  # no real ingestion
    ):
        yield mock


@pytest.fixture
def mock_qa():
    from uuid import UUID

    from api.schemas import AnswerResponse

    canned = AnswerResponse(
        answer="Canned answer",
        sources=[],
        session_id=UUID("00000000-0000-0000-0000-000000000001"),
    )

    async def fake_stream(*args, **kwargs):
        yield {"type": "token", "data": "Canned "}
        yield {"type": "token", "data": "answer"}
        yield {"type": "sources", "data": []}
        yield {"type": "done"}

    with (
        patch("api.routes.get_answer", return_value=canned),
        patch("api.routes.astream_answer", side_effect=fake_stream, create=True),
    ):
        yield


@pytest.fixture
def mock_evaluate():
    canned = {"faithfulness": 0.9, "answer_relevancy": 0.85, "context_precision": 0.8}
    with patch("api.routes.score_single", return_value=canned):
        yield canned


@pytest.fixture
def client(mock_vector_store, mock_qa, mock_evaluate):
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app, headers={"X-API-Key": "test-key-alice"}) as c:
        yield c


@pytest.fixture
def bob_client(client):
    """Second tenant sharing the same app/mocks as `client`."""
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app, headers={"X-API-Key": "test-key-bob"}) as c:
        yield c


@pytest.fixture
def anon_client(client):
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as c:
        yield c
