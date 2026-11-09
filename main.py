import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import router as api_router
from core import observability
from core.config import get_settings
from core.health import check_dependencies
from core.logging import setup_logging
from services.document_registry import document_registry
from services.job_queue import close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    observability.init_sentry(settings.SENTRY_DSN, settings.ENVIRONMENT)
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
    # Documents stuck in "processing" (e.g. a crash lost the job) become "failed".
    await asyncio.to_thread(document_registry.fail_stale, settings.INGEST_STALE_MINUTES)
    yield
    await close_pool()


app = FastAPI(
    title="Agentic RAG Document Intelligence API",
    description="Upload documents, ask questions, get cited answers with streaming and RAGAS evaluation.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
observability.install(app)  # added last => outermost, wraps CORS and routes

# Versioned API. The unprefixed routes remain for existing clients; new clients
# should use /v1.
app.include_router(api_router, prefix="/v1")
app.include_router(api_router, include_in_schema=False)


@app.get("/healthz", tags=["meta"])
async def healthz():
    """Liveness: the process is up. Never touches dependencies."""
    return {"status": "ok"}


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.get("/readyz", tags=["meta"])
async def readyz():
    """Readiness: all configured dependencies answer. 503 takes the pod out of rotation."""
    results = await check_dependencies()
    ok = all(v == "ok" for v in results.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "unavailable", "checks": results},
    )
