import asyncio
import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import BackgroundTasks

from core.config import get_settings
from services.ingestion import ingest_document

logger = logging.getLogger(__name__)

_pool = None
_pool_lock: Optional[asyncio.Lock] = None


async def _get_pool():
    global _pool, _pool_lock
    if _pool is not None:
        return _pool
    if _pool_lock is None:
        _pool_lock = asyncio.Lock()
    async with _pool_lock:
        if _pool is None:
            from arq import create_pool
            from arq.connections import RedisSettings

            _pool = await create_pool(RedisSettings.from_dsn(get_settings().REDIS_URL))
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enqueue_ingestion(
    background_tasks: BackgroundTasks,
    doc_id: UUID,
    file_path: Path,
    file_type: str,
    filename: str,
    owner_id: str,
) -> None:
    """Queue ingestion on the Redis/ARQ worker when REDIS_URL is set, otherwise
    fall back to an in-process background task (single-instance dev mode).

    Raises if the queue is configured but unreachable.
    """
    if not get_settings().REDIS_URL:
        background_tasks.add_task(ingest_document, doc_id, file_path, file_type, filename, owner_id)
        return

    pool = await _get_pool()
    # _job_id makes enqueueing idempotent per document.
    await pool.enqueue_job(
        "ingest_job", str(doc_id), str(file_path), file_type, filename, owner_id,
        _job_id=str(doc_id),
    )
    logger.info(f"Queued ingestion job for document {doc_id}")
