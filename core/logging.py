import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# Set per request by RequestContextMiddleware; "-" outside a request.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Anything passed via `extra=` shows up as a top-level field.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload:
                payload[key] = value
        return json.dumps(payload, default=str)


def setup_logging(fmt: str | None = None, level: str | None = None) -> None:
    """Configure root logging. `fmt` is "json" or "text" (defaults to LOG_FORMAT)."""
    from core.config import get_settings

    settings = get_settings()
    fmt = fmt or settings.LOG_FORMAT
    level = level or settings.LOG_LEVEL

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
        )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # uvicorn/gunicorn loggers should flow through our handler, and the access
    # log is replaced by RequestContextMiddleware's structured line.
    for name in ("uvicorn", "uvicorn.error", "gunicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
