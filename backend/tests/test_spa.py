"""The FastAPI app serves the built SPA when a static dir is present."""

from fastapi.testclient import TestClient

from omnichain.main import create_app


def test_api_health_works_without_static_dir():
    # Local-dev default: no static dir mounted, API still responds.
    client = TestClient(create_app())
    assert client.get("/api/health").json() == {"status": "ok"}


def test_spa_index_served_when_static_dir_present(tmp_path):
    (tmp_path / "index.html").write_text("<html><body>omnichain spa</body></html>")
    app = create_app(static_dir=tmp_path)
    client = TestClient(app)

    root = client.get("/")
    assert root.status_code == 200
    assert "omnichain spa" in root.text

    # API routes still take precedence over the SPA catch-all mount.
    assert client.get("/api/health").json()["status"] == "ok"
