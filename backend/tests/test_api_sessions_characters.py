"""Tests for the session and character HTTP endpoints."""

from fastapi.testclient import TestClient

from omnichain.main import create_app
from omnichain.services.firestore_store import FirestoreStore, get_firestore_store
from tests.fakes import FakeFirestore


def _client() -> TestClient:
    app = create_app()
    store = FirestoreStore(client=FakeFirestore())
    app.dependency_overrides[get_firestore_store] = lambda: store
    return TestClient(app)


def _session_payload(**kw) -> dict:
    return {
        "concept": "Snape Dogg drops a trap album",
        "style_tone": "gritty 90s rap video",
        "gcs_bucket": "b",
        "gcs_folder": "f",
        **kw,
    }


def test_session_create_get_list_delete():
    client = _client()

    resp = client.post("/api/sessions", json=_session_payload())
    assert resp.status_code == 201
    session_id = resp.json()["id"]

    assert client.get(f"/api/sessions/{session_id}").status_code == 200
    assert [s["id"] for s in client.get("/api/sessions").json()] == [session_id]

    assert client.delete(f"/api/sessions/{session_id}").status_code == 204
    assert client.get(f"/api/sessions/{session_id}").status_code == 404


def test_get_missing_session_returns_404():
    assert _client().get("/api/sessions/nope").status_code == 404


def test_character_crud_endpoints():
    client = _client()

    resp = client.post(
        "/api/characters",
        json={"name": "Snape Dogg", "physical_traits": "gaunt, hooked nose"},
    )
    assert resp.status_code == 201
    char_id = resp.json()["id"]

    assert client.get(f"/api/characters/{char_id}").status_code == 200
    assert [c["id"] for c in client.get("/api/characters").json()] == [char_id]

    resp = client.put(
        f"/api/characters/{char_id}",
        json={
            "id": char_id,
            "name": "Snape Dogg",
            "physical_traits": "gaunt, hooked nose",
            "wardrobe": "puffer + chain",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["wardrobe"] == "puffer + chain"

    assert client.delete(f"/api/characters/{char_id}").status_code == 204
    assert client.get(f"/api/characters/{char_id}").status_code == 404


def test_list_characters_filters_by_scope():
    client = _client()
    client.post("/api/characters", json={"name": "G", "physical_traits": "x", "scope": "global"})
    client.post("/api/characters", json={"name": "S", "physical_traits": "y", "scope": "session"})

    resp = client.get("/api/characters", params={"scope": "global"})
    assert [c["name"] for c in resp.json()] == ["G"]


def test_attach_and_detach_character():
    client = _client()
    session_id = client.post("/api/sessions", json=_session_payload()).json()["id"]
    char_id = client.post(
        "/api/characters", json={"name": "Snape Dogg", "physical_traits": "gaunt"}
    ).json()["id"]

    resp = client.post(f"/api/sessions/{session_id}/characters/{char_id}")
    assert resp.status_code == 200
    assert resp.json()["character_ids"] == [char_id]

    resp = client.delete(f"/api/sessions/{session_id}/characters/{char_id}")
    assert resp.status_code == 200
    assert resp.json()["character_ids"] == []


def test_attach_missing_character_returns_404():
    client = _client()
    session_id = client.post("/api/sessions", json=_session_payload()).json()["id"]
    assert client.post(f"/api/sessions/{session_id}/characters/ghost").status_code == 404
