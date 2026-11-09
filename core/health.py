import asyncio
import logging

from core.config import get_settings

logger = logging.getLogger(__name__)

_TIMEOUT = 2.0


def _check_database() -> None:
    from services.document_registry import document_registry

    document_registry.count("__readyz__")  # cheap indexed query; proves the DB answers


def _check_redis() -> None:
    import redis

    client = redis.Redis.from_url(
        get_settings().REDIS_URL, socket_connect_timeout=_TIMEOUT, socket_timeout=_TIMEOUT
    )
    try:
        client.ping()
    finally:
        client.close()


def _check_chroma() -> None:
    import httpx

    s = get_settings()
    resp = httpx.get(f"http://{s.CHROMA_HOST}:{s.CHROMA_PORT}/api/v2/heartbeat", timeout=_TIMEOUT)
    resp.raise_for_status()


async def check_dependencies() -> dict[str, str]:
    """Probe every configured dependency. Returns {name: "ok" | "error"}.

    The LLM provider is deliberately not probed: it is billed/rate-limited and
    an outage there should not take the pod out of rotation.
    """
    s = get_settings()
    checks = {"database": _check_database}
    if s.REDIS_URL:
        checks["redis"] = _check_redis
    if s.CHROMA_HOST:
        checks["chroma"] = _check_chroma

    async def run(name, fn):
        try:
            await asyncio.wait_for(asyncio.to_thread(fn), timeout=_TIMEOUT + 1)
            return name, "ok"
        except Exception as exc:
            logger.warning(f"Readiness check failed: {name}: {exc}")
            return name, "error"

    return dict(await asyncio.gather(*(run(n, f) for n, f in checks.items())))
