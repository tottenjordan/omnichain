"""Wrapper around the google-genai Interactions API for video generation.

OmniChain generates every clip with ``gemini-omni-flash-preview`` through the
Interactions API. Conversational edits chain off ``previous_interaction_id``.
There is **no fallback** to any other model: a failure is raised as a
:class:`GenerationError` carrying the raw provider message so the UI can show it.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, cast

from google import genai

from omnichain.config import get_settings
from omnichain.errors import GenerationError

logger = logging.getLogger("omnichain.interactions")

_KEEP_SUFFIX = "Keep everything else the same."
_DEFAULT_DURATION_S = 8
_DEFAULT_ASPECT_RATIO = "16:9"


@dataclass(frozen=True)
class GeneratedClip:
    """Result of a generate/edit call."""

    interaction_id: str
    video_bytes: bytes | None
    video_uri: str | None
    mime_type: str | None


def _build_client() -> genai.Client:
    settings = get_settings()
    if settings.google_genai_use_vertexai:
        return genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
        )
    return genai.Client(api_key=settings.google_api_key)


class InteractionsClient:
    """Thin, logged, fallback-free wrapper over ``client.interactions``."""

    def __init__(self, client: genai.Client | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._client = client if client is not None else _build_client()
        self._model = model or settings.omni_model

    def generate_clip(
        self,
        compiled_prompt: str,
        *,
        duration_s: int = _DEFAULT_DURATION_S,
        reference_uris: list[str] | None = None,
        aspect_ratio: str = _DEFAULT_ASPECT_RATIO,
    ) -> GeneratedClip:
        """Generate a single clip from a compiled prompt (+ optional references)."""
        content: list[dict[str, object]] = [{"type": "text", "text": compiled_prompt}]
        content.extend({"type": "image", "uri": uri} for uri in reference_uris or [])
        task = "reference_to_video" if reference_uris else "text_to_video"
        return self._create(content, task=task, duration_s=duration_s, aspect_ratio=aspect_ratio)

    def edit_clip(
        self,
        previous_interaction_id: str,
        instruction: str,
        *,
        duration_s: int = _DEFAULT_DURATION_S,
        aspect_ratio: str = _DEFAULT_ASPECT_RATIO,
    ) -> GeneratedClip:
        """Edit an existing clip conversationally (one change per turn)."""
        prompt = f"{instruction.strip()} {_KEEP_SUFFIX}"
        content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
        return self._create(
            content,
            task="edit",
            duration_s=duration_s,
            aspect_ratio=aspect_ratio,
            previous_interaction_id=previous_interaction_id,
        )

    def _create(
        self,
        content: list[dict[str, object]],
        *,
        task: str,
        duration_s: int,
        aspect_ratio: str,
        previous_interaction_id: str | None = None,
    ) -> GeneratedClip:
        body: dict[str, object] = {
            "model": self._model,
            "input": content,
            "response_modalities": ["video"],
            "response_format": {
                "type": "video",
                "duration": f"{duration_s}s",
                "aspect_ratio": aspect_ratio,
                "delivery": "inline",
            },
            "generation_config": {"video_config": {"task": task}},
        }
        if previous_interaction_id is not None:
            body["previous_interaction_id"] = previous_interaction_id

        logger.info(
            "interactions_request",
            extra={
                "model": self._model,
                "task": task,
                "duration_s": duration_s,
                "previous_interaction_id": previous_interaction_id,
                "reference_count": sum(1 for c in content if c.get("type") == "image"),
            },
        )
        try:
            response = cast("Any", self._client).interactions.create(**body)
        except Exception as exc:
            msg = "Video generation failed"
            logger.exception(msg, extra={"model": self._model, "task": task})
            raise GenerationError(msg, detail=str(exc)) from exc

        clip = self._extract(response)
        logger.info(
            "interactions_response",
            extra={
                "interaction_id": clip.interaction_id,
                "has_bytes": clip.video_bytes is not None,
                "video_uri": clip.video_uri,
            },
        )
        return clip

    @staticmethod
    def _extract(response: object) -> GeneratedClip:
        interaction_id = getattr(response, "id", None)
        output_video = getattr(response, "output_video", None)
        if interaction_id is None or output_video is None:
            msg = "Interactions API returned no video output"
            raise GenerationError(msg, detail=repr(response)[:300])

        raw_data = getattr(output_video, "data", None)
        video_bytes = base64.b64decode(raw_data) if raw_data else None
        return GeneratedClip(
            interaction_id=interaction_id,
            video_bytes=video_bytes,
            video_uri=getattr(output_video, "uri", None),
            mime_type=getattr(output_video, "mime_type", None),
        )


@lru_cache
def get_interactions_client() -> InteractionsClient:
    """FastAPI dependency returning a shared InteractionsClient."""
    return InteractionsClient()
