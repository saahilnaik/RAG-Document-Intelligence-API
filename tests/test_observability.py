import json
import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from core.logging import JsonFormatter, request_id_ctx


def test_healthz_and_legacy_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/health").json() == {"status": "ok"}


def test_readyz_ok_with_in_process_backends(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "checks": {"database": "ok"}}


def test_readyz_503_when_dependency_down(client):
    with patch("core.health._check_database", side_effect=ConnectionError("db down")):
        r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["checks"]["database"] == "error"
    assert "db down" not in r.text


def test_probes_do_not_require_auth(anon_client):
    assert anon_client.get("/healthz").status_code == 200
    assert anon_client.get("/readyz").status_code in (200, 503)


def test_v1_prefix_and_legacy_routes_both_work(client):
    assert client.get("/v1/documents").status_code == 200
    assert client.get("/documents").status_code == 200


def test_v1_requires_auth(anon_client):
    assert anon_client.get("/v1/documents").status_code == 401


def test_response_has_generated_request_id(client):
    rid = client.get("/healthz").headers["x-request-id"]
    assert len(rid) >= 16


def test_valid_client_request_id_is_propagated(client):
    r = client.get("/healthz", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"


def test_malformed_request_id_is_replaced(client):
    r = client.get("/healthz", headers={"X-Request-ID": 'bad id"; drop'})
    assert r.headers["x-request-id"] != 'bad id"; drop'
    assert r.headers["x-request-id"].isalnum()


def test_metrics_record_route_template_not_raw_path(client):
    from uuid import uuid4

    client.get(f"/v1/documents/{uuid4()}")  # 404 for an unknown id
    body = client.get("/metrics").text
    assert 'route="/v1/documents/{id}"' in body
    assert 'status="404"' in body
    assert "http_request_duration_seconds_bucket" in body


def test_probe_endpoints_excluded_from_request_metrics(client):
    client.get("/healthz")
    assert 'route="/healthz"' not in client.get("/metrics").text


def test_unhandled_error_returns_generic_500_with_request_id():
    from main import app

    async def boom():
        raise RuntimeError("secret internals")

    app.add_api_route("/__boom", boom)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/__boom", headers={"X-Request-ID": "trace-1"})
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error.", "request_id": "trace-1"}
    assert "secret" not in r.text


def test_json_formatter_includes_request_id_and_extras():
    token = request_id_ctx.set("req-42")
    try:
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello %s", ("world",), None)
        record.request_id = request_id_ctx.get()
        record.status = 200
        out = json.loads(JsonFormatter().format(record))
    finally:
        request_id_ctx.reset(token)
    assert out["message"] == "hello world"
    assert out["request_id"] == "req-42"
    assert out["status"] == 200
    assert out["level"] == "INFO"


@pytest.mark.parametrize("fmt", ["json", "text"])
def test_setup_logging_both_formats(fmt):
    from core.logging import setup_logging

    root = logging.getLogger()
    saved, level = root.handlers[:], root.level
    try:
        setup_logging(fmt=fmt, level="WARNING")
        assert len(root.handlers) == 1 and root.level == logging.WARNING
    finally:
        root.handlers, root.level = saved, level
