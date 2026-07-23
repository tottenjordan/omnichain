<!-- TODO: replace with a real banner image at imgs/omnichain_banner.png -->
<!--
[![OmniChain — AI Parody & Mashup Video Studio](imgs/omnichain_banner.png)](imgs/omnichain_banner.png)
-->

# 🎬 OmniChain 🪄

[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![uv](https://img.shields.io/badge/packaging-uv-DE5FE9?logo=uv&logoColor=white)](https://docs.astral.sh/uv/)
[![ruff](https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff&logoColor=black)](https://docs.astral.sh/ruff/)
[![ty](https://img.shields.io/badge/types-ty-261230)](https://github.com/astral-sh/ty)
[![Google ADK](https://img.shields.io/badge/agents-Google%20ADK-4285F4?logo=google&logoColor=white)](https://adk.dev/)
[![Vertex AI](https://img.shields.io/badge/Gemini%20Enterprise-Agent%20Platform-34A853?logo=googlecloud&logoColor=white)](https://docs.cloud.google.com/gemini-enterprise-agent-platform)
[![Gemini Omni Flash](https://img.shields.io/badge/video-gemini--omni--flash--preview-FBBC04?logo=googlegemini&logoColor=black)](https://ai.google.dev/gemini-api/docs/omni)
[![FastAPI](https://img.shields.io/badge/api-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Pytest](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)

> **AI Parody & Mashup Video Studio** — inspired by viral sensations like **Dripwarts** (Snape Dogg, DumbleDior). OmniChain blends multiple IPs and subcultures into cohesive 30–60s parody videos, powered by `gemini-omni-flash-preview` for unified multimodal video with native synced audio and conversational edits.

OmniChain hides Omni Flash's **10-second generation limit** behind a director-style workflow. You give it one high-level vision; a **Storyboard Agent** slices it into 3–6 sub-10s shots, a **Prompt Compiler** rewrites each shot into a rigid *"Anchor & Inject"* prompt (defeating character decay when mixing IPs), Omni Flash generates each clip through the **Interactions API**, you refine any clip via conversational diffing (`previous_interaction_id`, one change per turn), and FFmpeg stitches the approved clips — laying your master audio track over the final cut.

## Pipeline

1. **The Vision** — concept + Style/Tone, optional master audio, reference images, and a target GCS bucket/folder.
2. **The Storyboard** — the agent slices the vision into editable ≤10s shot cards.
3. **The Dailies** — clips generate side-by-side; refine any one with a chat (one change per turn).
4. **The Final Cut** — FFmpeg concatenates approved clips and muxes the master track.

## Tech stack

Python 3.12 · `uv` · `ruff` · `ty` · `pytest` · FastAPI · React (Vite + TS) · Google ADK · `google-genai` (Interactions API) · GCS · Firestore · FFmpeg · Cloud Run.

## Development

See [CODE_STANDARDS.md](CODE_STANDARDS.md). Backend uses `uv` for everything:

```bash
cd backend
uv sync --all-groups
uv run pytest
uv run ruff check . && uv run ty check src/
uv run uvicorn omnichain.main:app --reload
```

> **Note:** OmniChain never falls back to Veo. All generation errors surface directly in the UI.
