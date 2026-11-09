"""ARQ ingestion worker.  Run with:  arq worker.WorkerSettings

Shares the upload volume, Redis, Postgres and Chroma server with the API.
"""
import asyncio
import logging
from pathlib import Path
from uuid import UUID

from arq import Retry
from arq.connections import RedisSettings

from core.config import get_settings
from core.logging import setup_logging
from core.observability import INGESTION_RESULTS
from services.document_registry import document_registry
from services.ingestion import GENERIC_FAILURE, run_ingestion

logger = logging.getLogger(__name__)
_settings = get_settings()


async def ingest_job(ctx, doc_id: str, file_path: str, file_type: str, filename: str, owner_id: str):
    try:
        await asyncio.to_thread(
            run_ingestion, UUID(doc_id), Path(file_path), file_type, filename, owner_id
        )
    except Exception as exc:
        tries = ctx.get("job_try", 1)
        logger.error(f"Ingestion attempt {tries} failed for {doc_id}: {exc}", exc_info=True)
        if tries >= _settings.INGEST_MAX_TRIES:
            INGESTION_RESULTS.labels("failed").inc()
            await asyncio.to_thread(document_registry.mark_failed, UUID(doc_id), GENERIC_FAILURE)
            return
        raise Retry(defer=tries * 10) from exc


async def on_startup(ctx):
    setup_logging()
    swept = await asyncio.to_thread(document_registry.fail_stale, _settings.INGEST_STALE_MINUTES)
    if swept:
        logger.warning(f"Marked {swept} stale document(s) as failed")


class WorkerSettings:
    functions = [ingest_job]
    on_startup = on_startup
    redis_settings = RedisSettings.from_dsn(_settings.REDIS_URL or "redis://localhost:6379/0")
    max_tries = _settings.INGEST_MAX_TRIES
    job_timeout = 900
    max_jobs = 2  # embedding is CPU-heavy; keep concurrency low
