"""Tests for the per-shot edit endpoint and the session assembly endpoint."""

from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from omnichain.main import create_app
from omnichain.models.schemas import Session, Shot, ShotStatus, ShotVersion
from omnichain.services.ffmpeg_service import FfmpegService, get_ffmpeg_service
from omnichain.services.firestore_store import FirestoreStore, get_firestore_store
from omnichain.services.gcs_service import GcsService, get_gcs_service
from omnichain.services.interactions import (
    GeneratedClip,
    get_interactions_client,
)
from tests.fakes import FakeFirestore

_CLIP = b"FAKE-MP4"


class _StubInteractions:
    def __init__(self, clip: GeneratedClip) -> None:
        self.clip = clip
        self.edit_calls: list[dict] = []

    def edit_clip(self, previous_interaction_id, instruction, **kw):
        self.edit_calls.append({"prev": previous_interaction_id, "instruction": instruction, **kw})
        return self.clip


class _FakeFfmpegRunner:
    """Records argv and materializes the output file so it can be uploaded."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> None:
        self.commands.append(cmd)
        Path(cmd[-1]).write_bytes(b"FINAL-CUT")


def _gcs_mock() -> MagicMock:
    gcs = MagicMock(spec=GcsService)
    gcs.upload_bytes.side_effect = lambda bucket, path, *a, **k: f"gs://{bucket}/{path}"
    gcs.download_bytes.return_value = _CLIP
    gcs.signed_url.return_value = "https://signed.example/final.mp4"
    return gcs


def _app_with(store, *, interactions=None, gcs=None, ffmpeg=None):
    app = create_app()
    app.dependency_overrides[get_firestore_store] = lambda: store
    if interactions is not None:
        app.dependency_overrides[get_interactions_client] = lambda: interactions
    if gcs is not None:
        app.dependency_overrides[get_gcs_service] = lambda: gcs
    if ffmpeg is not None:
        app.dependency_overrides[get_ffmpeg_service] = lambda: ffmpeg
    return app


def _seed_generated_session(store: FirestoreStore) -> Session:
    session = Session(
        concept="c",
        style_tone="gritty",
        gcs_bucket="my-bucket",
        gcs_folder="proj",
        shots=[
            Shot(
                index=0,
                duration_s=8,
                draft_text="snape raps",
                interaction_id="int_1",
                status=ShotStatus.GENERATED,
                versions=[
                    ShotVersion(
                        version=1,
                        interaction_id="int_1",
                        clip_uri="gs://my-bucket/proj/sessions/s/shots/x/clip_v1.mp4",
                    )
                ],
            )
        ],
    )
    store.create_session(session)
    return session


# --- edit endpoint ---------------------------------------------------------


def test_edit_creates_next_version_via_previous_interaction():
    store = FirestoreStore(client=FakeFirestore())
    session = _seed_generated_session(store)
    shot_id = session.shots[0].id
    interactions = _StubInteractions(
        GeneratedClip(
            interaction_id="int_2", video_bytes=_CLIP, video_uri=None, mime_type="video/mp4"
        )
    )
    app = _app_with(store, interactions=interactions, gcs=_gcs_mock())
    client = TestClient(app)

    resp = client.post(
        f"/api/sessions/{session.id}/shots/{shot_id}/edit",
        json={"instruction": "Change the jacket to green"},
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 2
    # chained off the prior interaction id
    assert interactions.edit_calls[0]["prev"] == "int_1"

    stored = store.get_session(session.id).shots[0]
    assert len(stored.versions) == 2
    assert stored.versions[1].instruction == "Change the jacket to green"
    assert stored.interaction_id == "int_2"


def test_edit_rejects_multiple_changes():
    store = FirestoreStore(client=FakeFirestore())
    session = _seed_generated_session(store)
    shot_id = session.shots[0].id
    interactions = _StubInteractions(
        GeneratedClip(interaction_id="int_2", video_bytes=_CLIP, video_uri=None, mime_type=None)
    )
    app = _app_with(store, interactions=interactions, gcs=_gcs_mock())
    client = TestClient(app)

    resp = client.post(
        f"/api/sessions/{session.id}/shots/{shot_id}/edit",
        json={"instruction": "Change the jacket to green and add a red hat"},
    )
    assert resp.status_code == 400
    # provider was never called for a rejected multi-change edit
    assert interactions.edit_calls == []


def test_edit_before_generation_is_rejected():
    store = FirestoreStore(client=FakeFirestore())
    session = Session(
        concept="c",
        style_tone="t",
        gcs_bucket="b",
        gcs_folder="f",
        shots=[Shot(index=0, duration_s=8, draft_text="d")],
    )
    store.create_session(session)
    shot_id = session.shots[0].id
    app = _app_with(store, interactions=_StubInteractions(None), gcs=_gcs_mock())
    client = TestClient(app)

    resp = client.post(
        f"/api/sessions/{session.id}/shots/{shot_id}/edit",
        json={"instruction": "Change the jacket to green"},
    )
    assert resp.status_code == 409


# --- approve + assemble ----------------------------------------------------


def test_approve_marks_shot_approved():
    store = FirestoreStore(client=FakeFirestore())
    session = _seed_generated_session(store)
    shot_id = session.shots[0].id
    app = _app_with(store)
    client = TestClient(app)

    resp = client.post(f"/api/sessions/{session.id}/shots/{shot_id}/approve")
    assert resp.status_code == 200
    assert store.get_session(session.id).shots[0].status == ShotStatus.APPROVED


def test_assemble_concats_approved_clips_and_uploads_final():
    store = FirestoreStore(client=FakeFirestore())
    session = _seed_generated_session(store)
    session.shots[0].status = ShotStatus.APPROVED
    store.update_session(session)

    gcs = _gcs_mock()
    runner = _FakeFfmpegRunner()
    ffmpeg = FfmpegService(runner=runner)
    app = _app_with(store, gcs=gcs, ffmpeg=ffmpeg)
    client = TestClient(app)

    resp = client.post(f"/api/sessions/{session.id}/assemble")
    assert resp.status_code == 200
    body = resp.json()
    assert body["shot_count"] == 1
    assert body["signed_url"] == "https://signed.example/final.mp4"

    # final cut uploaded to the canonical path
    up = gcs.upload_bytes.call_args
    assert up.args[0] == "my-bucket"
    assert up.args[1] == f"proj/sessions/{session.id}/final/final_cut.mp4"
    # no master track → concat only, native audio untouched
    assert all("amix" not in " ".join(cmd) for cmd in runner.commands)


def test_assemble_with_master_audio_ducks():
    store = FirestoreStore(client=FakeFirestore())
    session = _seed_generated_session(store)
    session.master_audio_uri = "gs://my-bucket/proj/master.mp3"
    session.shots[0].status = ShotStatus.APPROVED
    store.update_session(session)

    runner = _FakeFfmpegRunner()
    ffmpeg = FfmpegService(runner=runner)
    app = _app_with(store, gcs=_gcs_mock(), ffmpeg=ffmpeg)
    client = TestClient(app)

    resp = client.post(f"/api/sessions/{session.id}/assemble")
    assert resp.status_code == 200
    # ducking mux ran over the concat output
    assert any("amix=inputs=2" in " ".join(cmd) for cmd in runner.commands)


def test_assemble_without_approved_shots_errors():
    store = FirestoreStore(client=FakeFirestore())
    session = _seed_generated_session(store)  # shot is GENERATED, not APPROVED
    app = _app_with(store, gcs=_gcs_mock(), ffmpeg=FfmpegService(runner=_FakeFfmpegRunner()))
    client = TestClient(app)

    resp = client.post(f"/api/sessions/{session.id}/assemble")
    assert resp.status_code == 502
    assert resp.json()["error"]["type"] == "assembly_error"
