"""Prompt Compiler: rewrite a shot draft into the Anchor & Inject prompt.

The LLM produces the six creative parts as JSON; a deterministic assembly step
then formats them in the fixed 6-part order, injects character anchor traits,
declares image-role references for characters that carry a reference image, and
appends the single-scene + duration cue. Keeping assembly deterministic makes
the character-binding rules testable without a live model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from omnichain.agents.parsing import parse_json
from omnichain.config import get_settings
from omnichain.errors import AgentError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from omnichain.models.schemas import Character

logger = logging.getLogger("omnichain.compiler")

_GUIDING_SUFFIX = "Use the given image(s) as references for video generation."
_PART_FIELDS = (
    ("subject_anchor", "[SUBJECT ANCHOR]"),
    ("aesthetic_injection", "[AESTHETIC INJECTION]"),
    ("environment", "[ENVIRONMENT]"),
    ("camera_lighting", "[CAMERA/LIGHTING]"),
    ("motion", "[MOTION]"),
    ("audio", "[AUDIO]"),
)

_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "compiler_system.md"


@dataclass(frozen=True)
class PromptParts:
    """The six creative fields produced by the compiler LLM."""

    subject_anchor: str
    aesthetic_injection: str
    environment: str
    camera_lighting: str
    motion: str
    audio: str


@dataclass(frozen=True)
class CompiledPrompt:
    """A fully assembled, generation-ready prompt."""

    text: str
    task: str
    reference_uris: list[str] = field(default_factory=list)


def _load_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def parse_parts(raw: str) -> PromptParts:
    """Parse the compiler LLM's JSON output into validated PromptParts."""
    data = parse_json(raw, what="Prompt compiler")
    if not isinstance(data, dict):
        msg = "Prompt compiler must return a JSON object"
        raise AgentError(msg, detail=repr(data)[:200])
    values: dict[str, str] = {}
    for key, _label in _PART_FIELDS:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            msg = f"Prompt compiler output is missing '{key}'"
            raise AgentError(msg, detail=repr(data)[:200])
        values[key] = value.strip()
    return PromptParts(**values)


def _character_anchor(character: Character) -> str:
    bits = [character.name, f"({character.physical_traits})"]
    if character.wardrobe:
        bits.append(f"wearing {character.wardrobe}")
    return " ".join(bits)


def assemble_prompt(
    parts: PromptParts,
    *,
    characters: list[Character],
    duration_s: int,
) -> CompiledPrompt:
    """Format parts + character bindings into the final Anchor & Inject prompt."""
    subject = parts.subject_anchor
    anchors = [_character_anchor(c) for c in characters]
    if anchors:
        subject = f"{subject} Featuring {'; '.join(anchors)}."

    lines = [f"{_PART_FIELDS[0][1]} {subject}"]
    lines += [f"{label} {getattr(parts, key)}" for key, label in _PART_FIELDS[1:]]

    referenced = [c for c in characters if c.reference_uri]
    reference_uris = [c.reference_uri for c in referenced if c.reference_uri]
    if referenced:
        roles = " ".join(f"<IMAGE_REF_{i}>@{c.name}" for i, c in enumerate(referenced))
        lines.append("")
        lines.append(f"[# References {roles}]")
        lines.append(_GUIDING_SUFFIX)

    lines.append(f"Single continuous scene, approximately {duration_s} seconds.")

    task = "reference_to_video" if referenced else "text_to_video"
    return CompiledPrompt(text="\n".join(lines), task=task, reference_uris=reference_uris)


def _user_prompt(shot_draft: str, style_tone: str, duration_s: int) -> str:
    return (
        f"SHOT DRAFT:\n{shot_draft}\n\n"
        f"STYLE / TONE:\n{style_tone}\n\n"
        f"CLIP LENGTH: {duration_s} seconds (single continuous scene).\n\n"
        "Compile this into the six-part JSON per your instructions."
    )


class PromptCompiler:
    """Turns a shot draft + attached characters into a compiled prompt."""

    def __init__(
        self,
        *,
        model: str | None = None,
        run_fn: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        settings = get_settings()
        self._model = model or settings.storyboard_model
        self._run_fn = run_fn
        self._system_prompt = _load_system_prompt()

    async def compile(
        self,
        *,
        shot_draft: str,
        style_tone: str,
        duration_s: int,
        characters: list[Character],
    ) -> CompiledPrompt:
        raw = await self._run(_user_prompt(shot_draft, style_tone, duration_s))
        parts = parse_parts(raw)
        return assemble_prompt(parts, characters=characters, duration_s=duration_s)

    async def _run(self, prompt: str) -> str:
        if self._run_fn is not None:
            return await self._run_fn(prompt)
        return await self._run_via_adk(prompt)

    async def _run_via_adk(self, prompt: str) -> str:
        app_name = "omnichain-compiler"
        user_id = "system"
        try:
            agent = Agent(
                model=self._model,
                name="prompt_compiler",
                instruction=self._system_prompt,
            )
            session_service = InMemorySessionService()
            session = await session_service.create_session(app_name=app_name, user_id=user_id)
            runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
            message = genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])
            final = ""
            async for event in runner.run_async(
                user_id=user_id, session_id=session.id, new_message=message
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    final = "".join(part.text or "" for part in event.content.parts)
        except Exception as exc:
            msg = "Prompt compiler failed"
            logger.exception(msg)
            raise AgentError(msg, detail=str(exc)) from exc
        return final


@lru_cache
def get_prompt_compiler() -> PromptCompiler:
    """FastAPI dependency returning a shared PromptCompiler."""
    return PromptCompiler()
