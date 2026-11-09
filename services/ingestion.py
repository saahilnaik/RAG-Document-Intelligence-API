import logging
from pathlib import Path
from uuid import UUID

from core.observability import INGESTION_RESULTS
from services.document_processor import chunk_documents, extract_text
from services.document_registry import document_registry
from services.vector_store import vector_store_manager

logger = logging.getLogger(__name__)

GENERIC_FAILURE = "Could not process this document."


def run_ingestion(
    doc_id: UUID, file_path: Path, file_type: str, filename: str, owner_id: str
) -> int:
    """Extract, chunk, embed and store a document, then mark it ready.

    Raises on failure so callers (the queue worker) can decide whether to retry.
    Idempotent: any chunks from a previous partial attempt are removed first.
    """
    logger.info(f"Starting ingestion for document {doc_id} ({filename})")
    docs = extract_text(str(file_path), file_type)
    chunks = chunk_documents(docs, str(doc_id), filename)
    for chunk in chunks:
        chunk.metadata["owner_id"] = owner_id
    vector_store_manager.delete_document(str(doc_id))  # clear partial earlier attempt
    vector_store_manager.store_chunks(chunks)
    document_registry.mark_ready(doc_id, len(chunks))
    logger.info(f"Stored {len(chunks)} chunks for document {doc_id}")
    INGESTION_RESULTS.labels("ready").inc()
    return len(chunks)


def ingest_document(
    doc_id: UUID, file_path: Path, file_type: str, filename: str, owner_id: str
) -> None:
    """Fire-and-forget variant (no queue configured): failures mark the doc failed."""
    try:
        run_ingestion(doc_id, file_path, file_type, filename, owner_id)
    except Exception as exc:
        logger.error(f"Ingestion failed for {doc_id} ({filename}): {exc}", exc_info=True)
        INGESTION_RESULTS.labels("failed").inc()
        document_registry.mark_failed(doc_id, GENERIC_FAILURE)
