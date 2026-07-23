"""Tests for the storyboard agent (vision -> shots)."""

import json

import pytest
from fastapi.testclient import TestClient

from omnichain.agents.storyboard_agent import (
    StoryboardAgent,
    get_storyboard_agent,
    parse_shots,
)
from omnichain.errors import AgentError
from omnichain.main import create_app
from omnichain.services.firestore_store import FirestoreStore, get_firestore_store
from tests.fakes import FakeFirestore


def _raw(shots: list[dict]) -> str:
    return json.dumps({"shots": shots})


def test_parse_shots_valid_list():
    raw = _raw(
        [
            {"duration_s": 10, "draft_text": "Snape Dogg struts into the potions lab"},
            {"duration_s": 10, "draft_text": "close-up on the bubbling cauldron of lean"},
            {"duration_s": 10, "draft_text": "crowd of wizards throwing up gang signs"},
        ]
    )
    shots = parse_shots(raw, target_seconds=30)
    assert [s.index for s in shots] == [0, 1, 2]
    assert all(3 <= s.duration_s <= 10 for s in shots)
    assert shots[0].draft_text.startswith("Snape Dogg")


def test_parse_shots_strips_code_fences():
    inner = _raw([{"duration_s": 5, "draft_text": f"beat {i}"} for i in range(3)])
    raw = f"```json\n{inner}\n```"
    assert len(parse_shots(raw, target_seconds=15)) == 3


def test_parse_shots_accepts_bare_list():
    raw = json.dumps([{"duration_s": 5, "draft_text": f"beat {i}"} for i in range(4)])
    assert len(parse_shots(raw, target_seconds=20)) == 4


def test_parse_shots_clamps_duration():
    raw = _raw(
        [
            {"duration_s": 99, "draft_text": "a"},
            {"duration_s": 1, "draft_text": "b"},
            {"duration_s": 7, "draft_text": "c"},
        ]
    )
    shots = parse_shots(raw, target_seconds=30)
    assert [s.duration_s for s in shots] == [10, 3, 7]


@pytest.mark.parametrize("count", [2, 7])
def test_parse_shots_rejects_out_of_range_count(count):
    raw = _raw([{"duration_s": 5, "draft_text": "x"} for _ in range(count)])
    with pytest.raises(AgentError):
        parse_shots(raw, target_seconds=30)


def test_parse_shots_rejects_bad_json():
    with pytest.raises(AgentError):
        parse_shots("not json at all", target_seconds=30)


async def test_generate_uses_injected_run_fn():
    canned = _raw([{"duration_s": 10, "draft_text": f"beat {i}"} for i in range(3)])

    async def fake_run(_prompt: str) -> str:
        return canned

    agent = StoryboardAgent(model="fake-model", run_fn=fake_run)
    shots = await agent.generate(concept="c", style_tone="t", target_seconds=30)
    assert [s.index for s in shots] == [0, 1, 2]


def test_storyboard_endpoint_populates_session():
    app = create_app()
    store = FirestoreStore(client=FakeFirestore())
    app.dependency_overrides[get_firestore_store] = lambda: store

    canned = _raw([{"duration_s": 10, "draft_text": f"beat {i}"} for i in range(3)])

    async def fake_run(_prompt: str) -> str:
        return canned

    app.dependency_overrides[get_storyboard_agent] = lambda: StoryboardAgent(
        model="fake-model", run_fn=fake_run
    )
    client = TestClient(app)

    session_id = client.post(
        "/api/sessions",
        json={"concept": "c", "style_tone": "t", "gcs_bucket": "b", "gcs_folder": "f"},
    ).json()["id"]

    resp = client.post(f"/api/sessions/{session_id}/storyboard", json={"target_seconds": 30})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["shots"]) == 3
    assert body["shots"][0]["draft_text"] == "beat 0"

    # persisted
    assert len(client.get(f"/api/sessions/{session_id}").json()["shots"]) == 3
