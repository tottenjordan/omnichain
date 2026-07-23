"""Tests for the Anchor & Inject prompt compiler."""

import json

import pytest

from omnichain.agents.prompt_compiler import (
    PromptCompiler,
    PromptParts,
    assemble_prompt,
    parse_parts,
)
from omnichain.errors import AgentError
from omnichain.models.schemas import Character

_PART_LABELS = [
    "[SUBJECT ANCHOR]",
    "[AESTHETIC INJECTION]",
    "[ENVIRONMENT]",
    "[CAMERA/LIGHTING]",
    "[MOTION]",
    "[AUDIO]",
]


def _parts(**kw) -> PromptParts:
    defaults = {
        "subject_anchor": "a rapper mid-verse",
        "aesthetic_injection": "gritty 90s VHS grain",
        "environment": "a smoky potions dungeon",
        "camera_lighting": "handheld, harsh top light",
        "motion": "slow push-in as he spits bars",
        "audio": "boom-bap beat, gravel vocals",
    }
    return PromptParts(**{**defaults, **kw})


def test_assemble_orders_six_parts():
    text = assemble_prompt(_parts(), characters=[], duration_s=8).text
    positions = [text.index(label) for label in _PART_LABELS]
    assert positions == sorted(positions)


def test_assemble_no_characters_is_text_to_video():
    compiled = assemble_prompt(_parts(), characters=[], duration_s=8)
    assert compiled.task == "text_to_video"
    assert compiled.reference_uris == []
    assert "[# References" not in compiled.text


def test_assemble_with_reference_character_injects_role_and_traits():
    char = Character(
        name="Snape Dogg",
        physical_traits="gaunt, hooked nose",
        wardrobe="black puffer + gold chain",
        reference_uri="gs://b/snape.png",
    )
    compiled = assemble_prompt(_parts(), characters=[char], duration_s=8)

    assert compiled.task == "reference_to_video"
    assert compiled.reference_uris == ["gs://b/snape.png"]
    assert "[# References <IMAGE_REF_0>@Snape Dogg]" in compiled.text
    assert "gaunt, hooked nose" in compiled.text
    assert "reference" in compiled.text.lower()  # guiding suffix present


def test_assemble_character_without_reference_injects_traits_only():
    char = Character(name="Dumblesnoop", physical_traits="long white beard")
    compiled = assemble_prompt(_parts(), characters=[char], duration_s=8)

    assert compiled.task == "text_to_video"
    assert compiled.reference_uris == []
    assert "long white beard" in compiled.text
    assert "[# References" not in compiled.text


def test_assemble_multiple_references_are_indexed():
    a = Character(name="A", physical_traits="tall", reference_uri="gs://b/a.png")
    b = Character(name="B", physical_traits="short", reference_uri="gs://b/b.png")
    compiled = assemble_prompt(_parts(), characters=[a, b], duration_s=8)

    assert "<IMAGE_REF_0>@A" in compiled.text
    assert "<IMAGE_REF_1>@B" in compiled.text
    assert compiled.reference_uris == ["gs://b/a.png", "gs://b/b.png"]


def test_assemble_includes_single_scene_and_duration_cue():
    text = assemble_prompt(_parts(), characters=[], duration_s=7).text.lower()
    assert "7" in text
    assert "single" in text
    assert "scene" in text


def test_parse_parts_missing_field_raises():
    raw = json.dumps({"subject_anchor": "x"})  # missing the rest
    with pytest.raises(AgentError):
        parse_parts(raw)


def test_parse_parts_strips_fences():
    payload = {
        "subject_anchor": "a",
        "aesthetic_injection": "b",
        "environment": "c",
        "camera_lighting": "d",
        "motion": "e",
        "audio": "f",
    }
    raw = f"```json\n{json.dumps(payload)}\n```"
    parts = parse_parts(raw)
    assert parts.subject_anchor == "a"


async def test_compile_uses_injected_run_fn():
    payload = {
        "subject_anchor": "a rapper mid-verse",
        "aesthetic_injection": "gritty",
        "environment": "dungeon",
        "camera_lighting": "harsh",
        "motion": "push-in",
        "audio": "boom-bap",
    }

    async def fake_run(_prompt: str) -> str:
        return json.dumps(payload)

    compiler = PromptCompiler(model="fake-model", run_fn=fake_run)
    compiled = await compiler.compile(
        shot_draft="snape raps in the dungeon",
        style_tone="gritty 90s rap video",
        duration_s=8,
        characters=[],
    )
    assert all(label in compiled.text for label in _PART_LABELS)
    assert compiled.task == "text_to_video"
