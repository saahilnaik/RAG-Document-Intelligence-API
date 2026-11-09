"""Request IDs, access logs, Prometheus metrics and the global error handler."""
import logging
import re
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

from core.logging import request_id_ctx

logger = logging.getLogger("access")

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency (time to response start; streams excluded)",
    ["method", "route"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
INGESTION_RESULTS = Counter("ingestion_total", "Document ingestion outcomes", ["outcome"])
NO_ANSWER = Counter("no_answer_total", "Questions with no sufficiently relevant context")
UNVERIFIED_CITATIONS = Counter(
    "unverified_citations_total", "Answers containing citations that match no retrieved chunk"
)
LLM_ERRORS = Counter("llm_errors_total", "Failed LLM/answer generations", ["path"])

_MAX_ID_LEN = 64


_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _route_template(request: Request) -> str:
    """Bounded-cardinality metric label.

    Only paths that matched a real route are reported (scanners hitting random
    URLs collapse into "unmatched"), with ids replaced by a placeholder. The
    matched route object's own path drops the /v1 prefix, so use the real path.
    """
    if request.scope.get("route") is None:
        return "unmatched"
    return _UUID_RE.sub("{id}", request.url.path)


class RequestContextMiddleware:
    """Pure-ASGI middleware (BaseHTTPMiddleware would buffer SSE streams)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")[:_MAX_ID_LEN]
        # Only trust well-formed client ids; otherwise generate our own.
        rid = incoming if incoming and incoming.replace("-", "").isalnum() else uuid4().hex
        scope["request_id"] = rid
        token = request_id_ctx.set(rid)
        start = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - start
            request = Request(scope)
            route = _route_template(request)
            if route not in ("/metrics", "/healthz", "/readyz", "/health"):
                HTTP_REQUESTS.labels(request.method, route, str(status["code"])).inc()
                HTTP_LATENCY.labels(request.method, route).observe(elapsed)
                logger.info(
                    "request",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status": status["code"],
                        "duration_ms": round(elapsed * 1000, 1),
                    },
                )
            request_id_ctx.reset(token)


def install(app: FastAPI) -> None:
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        # Details go to logs/Sentry only; clients get an id to quote in bug reports.
        logging.getLogger(__name__).error("Unhandled error", exc_info=exc)
        # Runs outside the middleware's context, so read the id from the ASGI scope.
        rid = request.scope.get("request_id", "-")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error.", "request_id": rid},
            headers={"x-request-id": rid},
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def init_sentry(dsn: str, environment: str) -> None:
    if not dsn:
        return
    import sentry_sdk

    sentry_sdk.init(dsn=dsn, environment=environment, traces_sample_rate=0.0, send_default_pii=False)
