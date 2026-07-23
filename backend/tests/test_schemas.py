"""Tests for OmniChain domain schemas."""

import pytest
from pydantic import ValidationError

from omnichain.models.schemas import (
    Character,
    CharacterScope,
    Session,
    Shot,
    ShotStatus,
    ShotVersion,
)


def test_character_round_trip():
    char = Character(
        name="Snape Dogg",
        physical_traits="gaunt man, hooked nose, shoulder-length black hair",
        wardrobe="oversized black puffer, diamond Cuban link chain",
        reference_uri="gs://bucket/chars/snape.png",
        scope=CharacterScope.GLOBAL,
    )
    restored = Character.model_validate(char.model_dump())
    assert restored == char
    assert restored.scope is CharacterScope.GLOBAL
    assert restored.id  # auto-generated


@pytest.mark.parametrize("bad", [2, 11, 0, -1])
def test_shot_duration_out_of_range_rejected(bad):
    with pytest.raises(ValidationError):
        Shot(index=0, duration_s=bad, draft_text="x")


@pytest.mark.parametrize("ok", [3, 7, 10])
def test_shot_duration_in_range_accepted(ok):
    shot = Shot(index=0, duration_s=ok, draft_text="x")
    assert shot.duration_s == ok
    assert shot.status is ShotStatus.PENDING
    assert shot.versions == []


def test_session_round_trip_with_nested_shots():
    session = Session(
        concept="Snape Dogg trap disstrack",
        style_tone="gritty 90s rap video",
        gcs_bucket="omnichain-media-hybrid-vertex",
        gcs_folder="dripwarts-ep1",
        character_ids=["char-1"],
        shots=[
            Shot(
                index=0,
                duration_s=8,
                draft_text="Snape enters the potions dungeon",
                versions=[ShotVersion(version=1, interaction_id="int-1", clip_uri="gs://b/c1.mp4")],
            )
        ],
    )
    restored = Session.model_validate(session.model_dump())
    assert restored == session
    assert restored.shots[0].versions[0].interaction_id == "int-1"
    assert restored.master_audio_uri is None
