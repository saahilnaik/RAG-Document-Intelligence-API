import threading
from datetime import UTC, datetime, timedelta
from typing import Optional, Protocol
from uuid import UUID

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.pool import StaticPool

from api.schemas import DocumentStatus
from core.config import get_settings


class DocumentRegistryBackend(Protocol):
    def register(self, doc_id: UUID, filename: str, owner_id: str = ...) -> DocumentStatus: ...
    def mark_ready(self, doc_id: UUID, chunk_count: int) -> None: ...
    def mark_failed(self, doc_id: UUID, error: str) -> None: ...
    def get(self, doc_id: UUID, owner_id: Optional[str] = ...) -> Optional[DocumentStatus]: ...
    def list_all(self, owner_id: Optional[str] = ...) -> list[DocumentStatus]: ...
    def count(self, owner_id: str) -> int: ...
    def delete(self, doc_id: UUID, owner_id: Optional[str] = ...) -> bool: ...
    def fail_stale(self, older_than_minutes: int) -> int: ...


_STALE_ERROR = "Processing did not finish. Please upload the document again."


class InMemoryDocumentRegistry:
    """Single-process registry (dev / tests). Reads are scoped by owner: a document
    owned by someone else behaves exactly like one that does not exist."""

    def __init__(self):
        self._store: dict[str, DocumentStatus] = {}
        self._lock = threading.Lock()

    def register(self, doc_id: UUID, filename: str, owner_id: str = "anonymous") -> DocumentStatus:
        entry = DocumentStatus(
            doc_id=doc_id,
            filename=filename,
            status="processing",
            created_at=datetime.now(UTC),
            owner_id=owner_id,
        )
        with self._lock:
            self._store[str(doc_id)] = entry
        return entry

    def mark_ready(self, doc_id: UUID, chunk_count: int) -> None:
        with self._lock:
            entry = self._store.get(str(doc_id))
            if entry:
                self._store[str(doc_id)] = entry.model_copy(
                    update={"status": "ready", "chunk_count": chunk_count, "error": None}
                )

    def mark_failed(self, doc_id: UUID, error: str) -> None:
        with self._lock:
            entry = self._store.get(str(doc_id))
            if entry:
                self._store[str(doc_id)] = entry.model_copy(
                    update={"status": "failed", "error": error}
                )

    def get(self, doc_id: UUID, owner_id: Optional[str] = None) -> Optional[DocumentStatus]:
        with self._lock:
            entry = self._store.get(str(doc_id))
        if entry is None or (owner_id is not None and entry.owner_id != owner_id):
            return None
        return entry

    def list_all(self, owner_id: Optional[str] = None) -> list[DocumentStatus]:
        with self._lock:
            entries = list(self._store.values())
        if owner_id is None:
            return entries
        return [e for e in entries if e.owner_id == owner_id]

    def count(self, owner_id: str) -> int:
        return len(self.list_all(owner_id))

    def delete(self, doc_id: UUID, owner_id: Optional[str] = None) -> bool:
        with self._lock:
            entry = self._store.get(str(doc_id))
            if entry is None or (owner_id is not None and entry.owner_id != owner_id):
                return False
            del self._store[str(doc_id)]
            return True

    def fail_stale(self, older_than_minutes: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
        n = 0
        with self._lock:
            for key, e in list(self._store.items()):
                if e.status == "processing" and e.created_at < cutoff:
                    self._store[key] = e.model_copy(update={"status": "failed", "error": _STALE_ERROR})
                    n += 1
        return n


_metadata = MetaData()
_documents = Table(
    "documents",
    _metadata,
    Column("doc_id", String(36), primary_key=True),
    Column("owner_id", String(255), nullable=False, index=True),
    Column("filename", String(255), nullable=False),
    Column("status", String(16), nullable=False),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("chunk_count", Integer, nullable=True),
)


class SqlDocumentRegistry:
    """Durable registry on any SQLAlchemy database (Postgres in production).

    Safe to share between multiple API replicas and the ingestion worker.
    """

    def __init__(self, url: str):
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            # Needed so an in-memory SQLite DB is shared across threads (tests).
            kwargs = {"connect_args": {"check_same_thread": False}}
            if ":memory:" in url or url in ("sqlite://", "sqlite:///"):
                kwargs["poolclass"] = StaticPool
        self._engine = create_engine(url, **kwargs)
        # Schema is created idempotently. Move to Alembic migrations once the
        # schema starts evolving.
        _metadata.create_all(self._engine)

    @staticmethod
    def _to_status(row) -> DocumentStatus:
        created = row.created_at
        if created.tzinfo is None:  # SQLite drops tzinfo
            created = created.replace(tzinfo=UTC)
        return DocumentStatus(
            doc_id=UUID(row.doc_id),
            filename=row.filename,
            status=row.status,
            error=row.error,
            created_at=created,
            chunk_count=row.chunk_count,
            owner_id=row.owner_id,
        )

    def register(self, doc_id: UUID, filename: str, owner_id: str = "anonymous") -> DocumentStatus:
        now = datetime.now(UTC)
        with self._engine.begin() as conn:
            conn.execute(
                insert(_documents).values(
                    doc_id=str(doc_id),
                    owner_id=owner_id,
                    filename=filename,
                    status="processing",
                    created_at=now,
                )
            )
        return DocumentStatus(
            doc_id=doc_id, filename=filename, status="processing", created_at=now, owner_id=owner_id
        )

    def mark_ready(self, doc_id: UUID, chunk_count: int) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                update(_documents)
                .where(_documents.c.doc_id == str(doc_id))
                .values(status="ready", chunk_count=chunk_count, error=None)
            )

    def mark_failed(self, doc_id: UUID, error: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                update(_documents)
                .where(_documents.c.doc_id == str(doc_id))
                .values(status="failed", error=error)
            )

    def get(self, doc_id: UUID, owner_id: Optional[str] = None) -> Optional[DocumentStatus]:
        stmt = select(_documents).where(_documents.c.doc_id == str(doc_id))
        if owner_id is not None:
            stmt = stmt.where(_documents.c.owner_id == owner_id)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
        return self._to_status(row) if row else None

    def list_all(self, owner_id: Optional[str] = None) -> list[DocumentStatus]:
        stmt = select(_documents).order_by(_documents.c.created_at)
        if owner_id is not None:
            stmt = stmt.where(_documents.c.owner_id == owner_id)
        with self._engine.connect() as conn:
            return [self._to_status(r) for r in conn.execute(stmt)]

    def count(self, owner_id: str) -> int:
        stmt = select(func.count()).select_from(_documents).where(_documents.c.owner_id == owner_id)
        with self._engine.connect() as conn:
            return int(conn.execute(stmt).scalar_one())

    def delete(self, doc_id: UUID, owner_id: Optional[str] = None) -> bool:
        stmt = delete(_documents).where(_documents.c.doc_id == str(doc_id))
        if owner_id is not None:
            stmt = stmt.where(_documents.c.owner_id == owner_id)
        with self._engine.begin() as conn:
            return conn.execute(stmt).rowcount > 0

    def fail_stale(self, older_than_minutes: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
        with self._engine.begin() as conn:
            res = conn.execute(
                update(_documents)
                .where(_documents.c.status == "processing", _documents.c.created_at < cutoff)
                .values(status="failed", error=_STALE_ERROR)
            )
        return res.rowcount


class _LazyRegistry:
    """Resolves the backend on first use so importing this module never reads
    settings or opens a connection (see 'Lazy initialization everywhere')."""

    def __init__(self):
        self._backend: Optional[DocumentRegistryBackend] = None
        self._lock = threading.Lock()

    def _resolve(self) -> DocumentRegistryBackend:
        if self._backend is None:
            with self._lock:
                if self._backend is None:
                    url = get_settings().DATABASE_URL
                    self._backend = SqlDocumentRegistry(url) if url else InMemoryDocumentRegistry()
        return self._backend

    def __getattr__(self, name: str):
        return getattr(self._resolve(), name)


document_registry = _LazyRegistry()
