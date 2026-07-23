"""Tests for the google-genai Interactions API wrapper."""

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from omnichain.errors import GenerationError
from omnichain.services.interactions import InteractionsClient

_CLIP = b"\x00\x01FAKE-MP4-BYTES"


def _fake_response(interaction_id: str = "int_123", *, data: bytes | None = _CLIP, uri=None):
    output_video = SimpleNamespace(
        data=base64.b64encode(data).decode() if data is not None else None,
        uri=uri,
        mime_type="video/mp4",
    )
    return SimpleNamespace(id=interaction_id, output_video=output_video)


def _client_with_response(response) -> tuple[InteractionsClient, MagicMock]:
    genai_client = MagicMock()
    genai_client.interactions.create.return_value = response
    return InteractionsClient(client=genai_client, model="gemini-omni-flash-preview"), genai_client


def test_generate_clip_calls_create_once_and_decodes_video():
    client, genai_client = _client_with_response(_fake_response())
    clip = client.generate_clip("A gritty 90s rap video of Snape Dogg", duration_s=8)

    genai_client.interactions.create.assert_called_once()
    kwargs = genai_client.interactions.create.call_args.kwargs
    assert kwargs["model"] == "gemini-omni-flash-preview"
    assert clip.interaction_id == "int_123"
    assert clip.video_bytes == _CLIP


def test_generate_clip_includes_prompt_and_default_task():
    client, genai_client = _client_with_response(_fake_response())
    client.generate_clip("prompt text", duration_s=6)
    kwargs = genai_client.interactions.create.call_args.kwargs
    dumped = str(kwargs["input"])
    assert "prompt text" in dumped
    assert kwargs["generation_config"]["video_config"]["task"] == "text_to_video"


def test_generate_clip_with_references_sets_reference_task():
    client, genai_client = _client_with_response(_fake_response())
    client.generate_clip(
        "prompt", duration_s=8, reference_uris=["gs://b/ref0.png", "gs://b/ref1.png"]
    )
    kwargs = genai_client.interactions.create.call_args.kwargs
    assert kwargs["generation_config"]["video_config"]["task"] == "reference_to_video"
    dumped = str(kwargs["input"])
    assert "gs://b/ref0.png" in dumped
    assert "gs://b/ref1.png" in dumped


def test_edit_clip_passes_previous_id_and_keep_suffix():
    client, genai_client = _client_with_response(_fake_response("int_456"))
    clip = client.edit_clip("int_123", "Change the jacket to green")

    kwargs = genai_client.interactions.create.call_args.kwargs
    assert kwargs["previous_interaction_id"] == "int_123"
    assert kwargs["generation_config"]["video_config"]["task"] == "edit"
    assert "Keep everything else the same" in str(kwargs["input"])
    assert clip.interaction_id == "int_456"


def test_generate_clip_wraps_errors_in_generation_error():
    genai_client = MagicMock()
    genai_client.interactions.create.side_effect = RuntimeError("provider exploded")
    client = InteractionsClient(client=genai_client, model="gemini-omni-flash-preview")

    with pytest.raises(GenerationError) as excinfo:
        client.generate_clip("prompt", duration_s=8)
    assert "provider exploded" in (excinfo.value.detail or "")


def test_uri_only_response_returns_uri_without_bytes():
    client, _ = _client_with_response(_fake_response(data=None, uri="gs://b/out.mp4"))
    clip = client.generate_clip("prompt", duration_s=8)
    assert clip.video_bytes is None
    assert clip.video_uri == "gs://b/out.mp4"


def test_no_veo_fallback_in_interactions_source():
    src = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "omnichain"
        / "services"
        / "interactions.py"
    )
    assert "veo" not in src.read_text(encoding="utf-8").lower()
