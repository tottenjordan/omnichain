"""Tests for the FastAPI app factory, error handling, and correlation ids."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import omnichain
from omnichain.errors import GenerationError
from omnichain.main import create_app


def _client_with_boom_routes() -> TestClient:
    app: FastAPI = create_app()

    @app.get("/api/_test/gen-error")
    def _gen_error() -> None:
        raise GenerationError("omni flash failed", detail="quota exceeded")

    @app.get("/api/_test/unexpected")
    def _unexpected() -> None:
        raise ValueError("boom")

    return TestClient(app, raise_server_exceptions=False)


def test_health_ok_and_correlation_header():
    client = TestClient(create_app())
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers.get("x-correlation-id")


def test_omnichain_error_shape():
    client = _client_with_boom_routes()
    resp = client.get("/api/_test/gen-error", headers={"X-Correlation-ID": "cid-abc"})
    assert resp.status_code == 502
    body = resp.json()["error"]
    assert body["type"] == "generation_error"
    assert body["message"] == "omni flash failed"
    assert body["detail"] == "quota exceeded"
    assert body["correlation_id"] == "cid-abc"


def test_unexpected_error_is_masked_500():
    client = _client_with_boom_routes()
    resp = client.get("/api/_test/unexpected", headers={"X-Correlation-ID": "cid-xyz"})
    assert resp.status_code == 500
    body = resp.json()["error"]
    assert body["type"] == "internal_error"
    # internal details are not leaked
    assert "boom" not in body["message"].lower()
    assert body["correlation_id"] == "cid-xyz"


def test_no_veo_fallback_anywhere_in_source():
    veo_markers = ("veo-2", "veo-3", "veo3", "veo_3", "generate_videos")
    root = Path(omnichain.__file__).parent
    offenders = {
        f"{path.name}:{marker}"
        for path in root.rglob("*.py")
        for marker in veo_markers
        if marker in path.read_text().lower()
    }
    assert not offenders, f"Veo usage/fallback detected: {offenders}"
