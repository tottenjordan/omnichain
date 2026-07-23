"""Tests for the GCS service and folder-browse endpoints."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from omnichain.errors import GcsError
from omnichain.main import create_app
from omnichain.services.gcs_service import GcsService, get_gcs_service


def _fake_client_with_prefixes(prefixes: set[str]) -> MagicMock:
    client = MagicMock()
    iterator = MagicMock()
    iterator.__iter__.return_value = iter([])
    iterator.prefixes = prefixes
    client.list_blobs.return_value = iterator
    return client


def test_list_folders_returns_sorted_names():
    client = _fake_client_with_prefixes({"sessions/", "characters/"})
    svc = GcsService(client=client)
    assert svc.list_folders("my-bucket") == ["characters", "sessions"]
    client.list_blobs.assert_called_once_with("my-bucket", delimiter="/")


def test_list_folders_wraps_errors_in_gcs_error():
    client = MagicMock()
    client.list_blobs.side_effect = RuntimeError("boom")
    svc = GcsService(client=client)
    with pytest.raises(GcsError):
        svc.list_folders("my-bucket")


def test_upload_bytes_returns_gs_uri():
    client = MagicMock()
    svc = GcsService(client=client)
    uri = svc.upload_bytes("b", "sessions/s1/clip.mp4", b"data", content_type="video/mp4")
    assert uri == "gs://b/sessions/s1/clip.mp4"
    client.bucket.return_value.blob.return_value.upload_from_string.assert_called_once()


def test_create_folder_creates_marker_object():
    client = MagicMock()
    svc = GcsService(client=client)
    assert svc.create_folder("b", "dripwarts-ep1") == "dripwarts-ep1"
    blob = client.bucket.return_value.blob
    blob.assert_called_once_with("dripwarts-ep1/")


def test_folders_endpoint_uses_service():
    app = create_app()
    fake = MagicMock(spec=GcsService)
    fake.list_folders.return_value = ["a", "b"]
    app.dependency_overrides[get_gcs_service] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/gcs/folders", params={"bucket": "my-bucket"})
    assert resp.status_code == 200
    assert resp.json() == {"bucket": "my-bucket", "folders": ["a", "b"]}
    fake.list_folders.assert_called_once_with("my-bucket")


def test_create_folder_endpoint():
    app = create_app()
    fake = MagicMock(spec=GcsService)
    fake.create_folder.return_value = "new-folder"
    app.dependency_overrides[get_gcs_service] = lambda: fake
    client = TestClient(app)

    resp = client.post("/api/gcs/folders", json={"bucket": "b", "folder": "new-folder"})
    assert resp.status_code == 201
    assert resp.json() == {"bucket": "b", "folder": "new-folder"}
