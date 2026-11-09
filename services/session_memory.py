import json
import threading
from collections import deque
from typing import Optional, Protocol
from uuid import UUID

from core.config import get_settings


def _key(session_id: UUID, owner_id: Optional[str]) -> str:
    # Namespacing by owner stops one user reading another's history by
    # guessing/reusing a session id.
    return f"{owner_id}:{session_id}" if owner_id else str(session_id)


class SessionMemoryBackend(Protocol):
    def get_turns(self, session_id: UUID, owner_id: Optional[str] = ...) -> list[dict]: ...
    def add_turn(
        self, session_id: UUID, question: str, answer: str, owner_id: Optional[str] = ...
    ) -> None: ...
    def clear(self, session_id: UUID, owner_id: Optional[str] = ...) -> None: ...


class InMemorySessionMemory:
    """Single-process memory (dev / tests). Lost on restart."""

    def __init__(self):
        self._sessions: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _get_or_create(self, session_id: str) -> deque:
        if session_id not in self._sessions:
            self._sessions[session_id] = deque(maxlen=get_settings().MAX_CONVERSATION_TURNS)
        return self._sessions[session_id]

    def get_turns(self, session_id: UUID, owner_id: Optional[str] = None) -> list[dict]:
        with self._lock:
            return list(self._get_or_create(_key(session_id, owner_id)))

    def add_turn(
        self, session_id: UUID, question: str, answer: str, owner_id: Optional[str] = None
    ) -> None:
        with self._lock:
            self._get_or_create(_key(session_id, owner_id)).append(
                {"question": question, "answer": answer}
            )

    def clear(self, session_id: UUID, owner_id: Optional[str] = None) -> None:
        with self._lock:
            self._sessions.pop(_key(session_id, owner_id), None)


class RedisSessionMemory:
    """Shared across API replicas; keeps the last N turns per session and
    expires idle sessions after SESSION_TTL_SECONDS."""

    def __init__(self, client):
        self._r = client

    @staticmethod
    def _rkey(session_id: UUID, owner_id: Optional[str]) -> str:
        return f"session:{_key(session_id, owner_id)}"

    def get_turns(self, session_id: UUID, owner_id: Optional[str] = None) -> list[dict]:
        raw = self._r.lrange(self._rkey(session_id, owner_id), 0, -1)
        return [json.loads(item) for item in raw]

    def add_turn(
        self, session_id: UUID, question: str, answer: str, owner_id: Optional[str] = None
    ) -> None:
        settings = get_settings()
        key = self._rkey(session_id, owner_id)
        pipe = self._r.pipeline()
        pipe.rpush(key, json.dumps({"question": question, "answer": answer}))
        pipe.ltrim(key, -settings.MAX_CONVERSATION_TURNS, -1)
        pipe.expire(key, settings.SESSION_TTL_SECONDS)
        pipe.execute()

    def clear(self, session_id: UUID, owner_id: Optional[str] = None) -> None:
        self._r.delete(self._rkey(session_id, owner_id))


class _LazySessionMemory:
    """Resolves the backend on first use (no settings read / connection at import)."""

    def __init__(self):
        self._backend: Optional[SessionMemoryBackend] = None
        self._lock = threading.Lock()

    def _resolve(self) -> SessionMemoryBackend:
        if self._backend is None:
            with self._lock:
                if self._backend is None:
                    url = get_settings().REDIS_URL
                    if url:
                        import redis

                        self._backend = RedisSessionMemory(
                            redis.Redis.from_url(url, decode_responses=True)
                        )
                    else:
                        self._backend = InMemorySessionMemory()
        return self._backend

    def __getattr__(self, name: str):
        return getattr(self._resolve(), name)


session_memory = _LazySessionMemory()
