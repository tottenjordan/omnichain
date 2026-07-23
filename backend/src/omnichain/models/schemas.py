"""Domain schemas for sessions, shots, and characters."""

from __future__ import annotations

import uuid
from enum import StrEnum

from pydantic import BaseModel, Field


class CharacterScope(StrEnum):
    """Whether a character lives in the reusable global library or one session."""

    GLOBAL = "global"
    SESSION = "session"


class ShotStatus(StrEnum):
    """Lifecycle of a single shot."""

    PENDING = "pending"
    COMPILED = "compiled"
    GENERATING = "generating"
    GENERATED = "generated"
    APPROVED = "approved"
    FAILED = "failed"


def _new_id() -> str:
    return uuid.uuid4().hex


class Character(BaseModel):
    """A reusable character description used to anchor prompts."""

    id: str = Field(default_factory=_new_id)
    name: str
    physical_traits: str
    wardrobe: str | None = None
    # https:// URL or gs:// URI to a reference image used for image-role binding.
    reference_uri: str | None = None
    scope: CharacterScope = CharacterScope.GLOBAL


class ShotVersion(BaseModel):
    """One generated/edited iteration of a shot's clip."""

    version: int = Field(ge=1)
    interaction_id: str
    clip_uri: str
    # The edit instruction that produced this version (None for the first gen).
    instruction: str | None = None


class Shot(BaseModel):
    """A single sub-10s beat of the storyboard."""

    id: str = Field(default_factory=_new_id)
    index: int = Field(ge=0)
    duration_s: int = Field(ge=3, le=10)
    draft_text: str
    compiled_prompt: str | None = None
    interaction_id: str | None = None  # latest interaction id for editing
    versions: list[ShotVersion] = Field(default_factory=list)
    status: ShotStatus = ShotStatus.PENDING


class Session(BaseModel):
    """A full parody-video project."""

    id: str = Field(default_factory=_new_id)
    concept: str
    style_tone: str
    gcs_bucket: str
    gcs_folder: str
    master_audio_uri: str | None = None
    character_ids: list[str] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)
