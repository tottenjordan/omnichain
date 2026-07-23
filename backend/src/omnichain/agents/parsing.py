"""Shared helpers for parsing LLM JSON output."""

from __future__ import annotations

import json
import re

from omnichain.errors import AgentError

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def strip_code_fences(raw: str) -> str:
    """Remove a leading/trailing ```json ... ``` fence if present."""
    return _FENCE_RE.sub("", raw).strip()


def parse_json(raw: str, *, what: str) -> object:
    """Parse fenced-or-bare JSON text, raising AgentError on failure."""
    text = strip_code_fences(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"{what} returned invalid JSON"
        raise AgentError(msg, detail=str(exc)) from exc
