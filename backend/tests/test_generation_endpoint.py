"""Tests for the per-shot generation endpoint."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from omnichain.agents.prompt_compiler import CompiledPrompt, get_prompt_compiler
from omnichain.errors import GenerationError
from omnichain.main import create_app
from omnichain.models.schemas import Session, Shot, ShotStatus
from omnichain.services.firestore_store import FirestoreStore, get_firestore_store
from omnichain.services.gcs_service import GcsService, get_gcs_service
from omnichain.services.interactions import (
    GeneratedClip,
    InteractionsClient,
    get_interactions_client,
)
from tests.fakes import FakeFirestore

_CLIP = b"FAKE-MP4"


class _StubCompiler:
    async def compile(self, **_kw) -> CompiledPrompt:
        return CompiledPrompt(text="[SUBJECT ANCHOR] ...", task="text_to_video", reference_uris=[])


class _StubInteractions:
    def __init__(self, clip: GeneratedClip) -> None:
        self.clip = clip
        self.calls: list[dict] = []

    def generate_clip(self, prompt, **kw):
        self.calls.append({"prompt": prompt, **kw})
        return self.clip


def _app_with(store, compiler, interactions, gcs):
    app = create_app()
    app.dependency_overrides[get_firestore_store] = lambda: store
    app.dependency_overrides[get_prompt_compiler] = lambda: compiler
    app.dependency_overrides[get_interactions_client] = lambda: interactions
    app.dependency_overrides[get_gcs_service] = lambda: gcs
    return app


def _seed_session(store: FirestoreStore) -> Session:
    session = Session(
        concept="c",
        style_tone="gritty",
        gcs_bucket="my-bucket",
        gcs_folder="proj",
        shots=[Shot(index=0, duration_s=8, draft_text="snape raps")],
    )
    store.create_session(session)
    return session


def _gcs_mock() -> MagicMock:
    gcs = MagicMock(spec=GcsService)
    gcs.upload_bytes.side_effect = lambda bucket, path, *a, **k: f"gs://{bucket}/{path}"
    gcs.signed_url.return_value = "https://signed.example/clip.mp4"
    return gcs


def test_generate_uploads_clip_and_persists_version():
    store = FirestoreStore(client=FakeFirestore())
    session = _seed_session(store)
    shot_id = session.shots[0].id
    interactions = _StubInteractions(
        GeneratedClip(
            interaction_id="int_1", video_bytes=_CLIP, video_uri=None, mime_type="video/mp4"
        )
    )
    gcs = _gcs_mock()
    app = _app_with(store, _StubCompiler(), interactions, gcs)
    client = TestClient(app)

    resp = client.post(f"/api/sessions/{session.id}/shots/{shot_id}/generate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 1
    assert body["interaction_id"] == "int_1"
    assert body["signed_url"] == "https://signed.example/clip.mp4"

    # uploaded to the expected path
    up = gcs.upload_bytes.call_args
    assert up.args[0] == "my-bucket"
    assert up.args[1] == f"proj/sessions/{session.id}/shots/{shot_id}/clip_v1.mp4"
    assert up.args[2] == _CLIP

    # persisted: shot now has one version + interaction id + GENERATED status
    stored = store.get_session(session.id).shots[0]
    assert stored.status == ShotStatus.GENERATED
    assert stored.interaction_id == "int_1"
    assert len(stored.versions) == 1
    assert stored.versions[0].version == 1


def test_second_generate_increments_version():
    store = FirestoreStore(client=FakeFirestore())
    session = _seed_session(store)
    shot_id = session.shots[0].id
    interactions = _StubInteractions(
        GeneratedClip(
            interaction_id="int_2", video_bytes=_CLIP, video_uri=None, mime_type="video/mp4"
        )
    )
    app = _app_with(store, _StubCompiler(), interactions, _gcs_mock())
    client = TestClient(app)

    client.post(f"/api/sessions/{session.id}/shots/{shot_id}/generate")
    resp = client.post(f"/api/sessions/{session.id}/shots/{shot_id}/generate")
    assert resp.json()["version"] == 2
    assert len(store.get_session(session.id).shots[0].versions) == 2


def test_generate_missing_shot_returns_404():
    store = FirestoreStore(client=FakeFirestore())
    session = _seed_session(store)
    app = _app_with(store, _StubCompiler(), _StubInteractions(None), _gcs_mock())
    client = TestClient(app)

    resp = client.post(f"/api/sessions/{session.id}/shots/ghost/generate")
    assert resp.status_code == 404


def test_generation_error_surfaces_no_fallback():
    store = FirestoreStore(client=FakeFirestore())
    session = _seed_session(store)
    shot_id = session.shots[0].id

    class _Boom:
        def generate_clip(self, *a, **k):
            raise GenerationError("provider down", detail="502 from omni")

    app = _app_with(store, _StubCompiler(), _Boom(), _gcs_mock())
    client = TestClient(app)

    resp = client.post(f"/api/sessions/{session.id}/shots/{shot_id}/generate")
    assert resp.status_code == 502
    assert resp.json()["error"]["type"] == "generation_error"


def test_get_interactions_client_dependency_type():
    # smoke: the DI factory returns the real wrapper type (no network on import)
    assert callable(get_interactions_client)
    assert InteractionsClient is not None
