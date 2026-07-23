"""Storyboard agent: decompose a vision into 3-6 sub-10s shots.

The LLM boundary is isolated behind ``run_fn`` so the prompt-building and
JSON-parsing logic can be unit-tested without ADK/genai. In production the
default path runs a Google ADK ``Agent`` via an in-memory ``Runner``.
"""

from __future__ import annotations

import logging
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
from omnichain.models.schemas import Shot

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger("omnichain.storyboard")

_MIN_SHOTS = 3
_MAX_SHOTS = 6
_MIN_DURATION = 3
_MAX_DURATION = 10

_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "storyboard_system.md"


def _load_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _user_prompt(concept: str, style_tone: str, target_seconds: int) -> str:
    return (
        f"CONCEPT:\n{concept}\n\n"
        f"STYLE / TONE:\n{style_tone}\n\n"
        f"TARGET LENGTH: about {target_seconds} seconds total.\n\n"
        "Decompose this into shots per your instructions and return the JSON object."
    )


def _clamp_duration(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        msg = f"Shot duration is not a number: {value!r}"
        raise AgentError(msg)
    try:
        seconds = int(float(value))
    except (TypeError, ValueError) as exc:
        msg = f"Shot duration is not a number: {value!r}"
        raise AgentError(msg) from exc
    return max(_MIN_DURATION, min(_MAX_DURATION, seconds))


def parse_shots(raw: str, target_seconds: int) -> list[Shot]:
    """Parse the agent's JSON output into validated, indexed ``Shot`` objects."""
    data = parse_json(raw, what="Storyboard agent")
    items = data.get("shots") if isinstance(data, dict) else data
    if not isinstance(items, list):
        msg = "Storyboard JSON must be a list of shots or {'shots': [...]}"
        raise AgentError(msg, detail=repr(data)[:200])

    if not (_MIN_SHOTS <= len(items) <= _MAX_SHOTS):
        msg = f"Storyboard must have {_MIN_SHOTS}-{_MAX_SHOTS} shots, got {len(items)}"
        raise AgentError(msg)

    shots: list[Shot] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            msg = f"Shot {index} is not an object"
            raise AgentError(msg, detail=repr(item)[:200])
        draft = item.get("draft_text") or item.get("description")
        if not isinstance(draft, str) or not draft.strip():
            msg = f"Shot {index} is missing draft_text"
            raise AgentError(msg, detail=repr(item)[:200])
        shots.append(
            Shot(
                index=index,
                duration_s=_clamp_duration(item.get("duration_s", _MAX_DURATION)),
                draft_text=draft.strip(),
            )
        )
    logger.info("storyboard_parsed", extra={"shot_count": len(shots), "target_s": target_seconds})
    return shots


class StoryboardAgent:
    """Turns a concept + style/tone into a list of editable shot drafts."""

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

    async def generate(
        self,
        concept: str,
        style_tone: str,
        target_seconds: int,
    ) -> list[Shot]:
        prompt = _user_prompt(concept, style_tone, target_seconds)
        raw = await self._run(prompt)
        return parse_shots(raw, target_seconds)

    async def _run(self, prompt: str) -> str:
        if self._run_fn is not None:
            return await self._run_fn(prompt)
        return await self._run_via_adk(prompt)

    async def _run_via_adk(self, prompt: str) -> str:
        app_name = "omnichain-storyboard"
        user_id = "system"
        try:
            agent = Agent(
                model=self._model,
                name="storyboard_director",
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
            msg = "Storyboard agent failed"
            logger.exception(msg)
            raise AgentError(msg, detail=str(exc)) from exc
        return final


@lru_cache
def get_storyboard_agent() -> StoryboardAgent:
    """FastAPI dependency returning a shared StoryboardAgent."""
    return StoryboardAgent()
