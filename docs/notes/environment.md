# Environment & tooling gotchas

Non-obvious facts about the dev/runtime environment for OmniChain, discovered
2026-07-23. Re-verify before relying on any of these.

## Not installed / blocked

- **`ffmpeg` is not installed** on the dev machine. Task 12 (assembly) tests mock
  the subprocess, so unit tests pass, but **live assembly and the Docker image
  (Task 15) must install ffmpeg**. Verify with `which ffmpeg`.
- **`WebSearch` is blocked** by an org policy (`constraints/vertexai.allowedPartnerModelFeatures`)
  on project `hybrid-vertex`. Use the `google-dev-knowledge` MCP tools or `WebFetch`
  for research instead.

## genai auth mode

- `.env` sets `GOOGLE_GENAI_USE_VERTEXAI=0`, i.e. dev uses the **Gemini Developer
  API with an API key** (`GEMINI_API_KEY`/`GOOGLE_API_KEY`), *not* Vertex. `config.py`
  supports both via the `google_genai_use_vertexai` flag. The `.env` also holds a
  **live API key** — it is gitignored; rotate if leaked.

## Python / tooling

- The `uv` venv is **Python 3.14.6** even though README/badges say 3.12. Ruff
  `target-version`/ty `python-version` are pinned to `py312` (syntax floor); code
  runs on 3.14.
- Starlette's `TestClient` emits a `StarletteDeprecationWarning` about `httpx` vs
  `httpx2`. Harmless; pytest is not set to error on warnings.

## FastAPI correlation id

- Correlation-id propagation uses a **pure-ASGI middleware** (`main.py`), not
  `BaseHTTPMiddleware`, because the latter runs the endpoint in a separate task and
  the contextvar would not propagate. See `CorrelationIdMiddleware`.

Related: [[README]] (notes index).
