import asyncio
import json
import logging
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from api.schemas import AnswerResponse, AskRequest, DocumentStatus, EvaluateRequest, EvaluateResponse, UploadResponse
from core.auth import get_current_user
from core.config import get_settings
from core.uploads import content_matches_extension, sanitize_filename
from services.document_registry import document_registry
from services.evaluation import score_single
from services.job_queue import enqueue_ingestion
from services.qa import astream_answer, get_answer
from services.vector_store import vector_store_manager

router = APIRouter(dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)


_READ_CHUNK = 1024 * 1024


@router.post("/upload", response_model=UploadResponse, status_code=202)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
) -> UploadResponse:
    settings = get_settings()
    filename = sanitize_filename(file.filename)

    suffix = Path(filename).suffix.lower()
    if suffix not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"File type {suffix!r} not supported. Allowed: {sorted(settings.ALLOWED_EXTENSIONS)}",
        )

    if document_registry.count(user_id) >= settings.MAX_DOCS_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=f"Document limit reached ({settings.MAX_DOCS_PER_USER}). Delete some first.",
        )

    # Read incrementally so an oversized upload is rejected without buffering it all.
    limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    parts: list[bytes] = []
    total = 0
    while chunk := await file.read(_READ_CHUNK):
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit.",
            )
        parts.append(chunk)
    contents = b"".join(parts)

    if not contents:
        raise HTTPException(status_code=400, detail="Empty file.")
    if not content_matches_extension(contents[:8192], suffix):
        raise HTTPException(
            status_code=415, detail=f"File content does not look like a valid {suffix} file."
        )

    doc_id = uuid4()
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{doc_id}{suffix}"
    file_path.write_bytes(contents)

    document_registry.register(doc_id, filename, user_id)
    try:
        await enqueue_ingestion(background_tasks, doc_id, file_path, suffix, filename, user_id)
    except Exception as exc:
        logger.error(f"Could not enqueue ingestion for {doc_id}", exc_info=True)
        document_registry.delete(doc_id, user_id)
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="Ingestion service unavailable. Try again shortly.") from exc

    return UploadResponse(doc_id=doc_id, filename=filename)


@router.get("/documents", response_model=list[DocumentStatus])
async def list_documents(user_id: str = Depends(get_current_user)) -> list[DocumentStatus]:
    return document_registry.list_all(user_id)


@router.get("/documents/{doc_id}", response_model=DocumentStatus)
async def get_document(doc_id: UUID, user_id: str = Depends(get_current_user)) -> DocumentStatus:
    entry = document_registry.get(doc_id, user_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")
    return entry


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: UUID, user_id: str = Depends(get_current_user)) -> None:
    entry = document_registry.get(doc_id, user_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")
    vector_store_manager.delete_document(str(doc_id))
    document_registry.delete(doc_id, user_id)
    for path in Path(get_settings().UPLOAD_DIR).glob(f"{doc_id}.*"):
        path.unlink(missing_ok=True)


def _check_doc_ready(doc_id: UUID, user_id: str) -> None:
    entry = document_registry.get(doc_id, user_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")
    if entry.status == "processing":
        raise HTTPException(status_code=409, detail="Document is still processing. Try again shortly.")
    if entry.status == "failed":
        raise HTTPException(status_code=422, detail=f"Document ingestion failed: {entry.error}")


@router.post("/ask", response_model=AnswerResponse)
async def ask(req: AskRequest, user_id: str = Depends(get_current_user)) -> AnswerResponse:
    if req.doc_id:
        _check_doc_ready(req.doc_id, user_id)
    return await asyncio.to_thread(get_answer, req.question, req.session_id, req.doc_id, user_id)


@router.post("/ask/stream")
async def ask_stream(
    req: AskRequest, user_id: str = Depends(get_current_user)
) -> StreamingResponse:
    if req.doc_id:
        _check_doc_ready(req.doc_id, user_id)

    async def event_generator():
        async for event in astream_answer(req.question, req.session_id, req.doc_id, user_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_answer(req: EvaluateRequest) -> EvaluateResponse:
    scores = await asyncio.to_thread(
        score_single,
        req.question,
        req.answer,
        req.contexts,
        req.ground_truth,
    )
    return EvaluateResponse(**scores)
