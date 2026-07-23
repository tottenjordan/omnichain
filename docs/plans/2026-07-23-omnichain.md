# OmniChain Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. On execution, copy this file to `docs/plans/2026-07-23-omnichain.md` per the `writing-plans` skill (the plan-mode harness restricted writes to the plan file only during planning).

**Goal:** A Python + React app that turns a single high-level concept into a cohesive 30–60s parody video by decomposing it into 3–6 sub-10s shots, compiling director-grade prompts, generating each shot with `gemini-omni-flash-preview` via the Interactions API, allowing conversational per-clip edits, and stitching the approved clips with FFmpeg.

**Architecture:** Single Cloud Run service = FastAPI backend serving a built React/Vite SPA. Two ADK agents run **in-process**: a *Storyboard Agent* (slices the vision) and a *Prompt Compiler* (rewrites shorthand into the rigid "Anchor & Inject" 6-part prompt). Video generation/editing goes through the `google-genai` Interactions API, chaining edits with `previous_interaction_id`. Durable app metadata lives in **Firestore** (Cloud Run is stateless); large assets (clips, refs, master audio, final cut) live in **GCS** under a user-chosen bucket/folder.

**Tech Stack:** Python 3.12, `uv`, `ruff`, `ty`, `pytest`; `fastapi` + `uvicorn`; `google-genai`, `google-adk`, `google-cloud-storage`, `google-cloud-firestore`; `ffmpeg` (via `ffmpeg-python` or subprocess); React + Vite + TypeScript; Docker → Cloud Run.

---

## Context

The user wants "OmniChain": a parody-video studio (à la the viral *Dripwarts* / OmniMash) that hides Omni Flash's **10-second hard limit** behind a director-style workflow. The core problems this design solves:

1. **10s cap → 30–60s output.** Decompose the vision into ≤10s shots, generate each, stitch with FFmpeg.
2. **Character decay when blending IPs.** A *Prompt Compiler* agent never passes raw user text; it expands into a rigid 6-part taxonomy with explicit subject anchors + reference-image role tags.
3. **Cheap conversational editing.** The Interactions API keeps latent state server-side; edits pass `previous_interaction_id` instead of re-uploading video. UI enforces Google's **one-change-per-turn** rule.
4. **Native synced audio.** Audio is steered inside the same prompt payload (`[AUDIO]` segment) — confirmed correct by the docs. The user's master track **cannot** be fed to Omni Flash (audio-reference upload is unsupported), so it is muxed over the final cut by FFmpeg, ducking the clips' native music bed.

### Verified API facts (from Gemini docs, 2026-07-23 — re-verify before coding)
- Model id `gemini-omni-flash-preview`; `DURATION` accepts `"3s"`–`"10s"`; native synced audio; ~720p.
- `client.interactions.create(model=, input=, previous_interaction_id=res1.id)` → returns `.id`, `.output_video.data` (base64) / `.output_video.uri`. `store=false` disables later editing; `background=true` = async, retained 14 days.
- Image roles: tags `<FIRST_FRAME>`, `<IMAGE_REF_N>` (N from 0); explicit form `[# References <IMAGE_REF_0>@Image1 <IMAGE_REF_1>@Image2]` + guiding suffix ("Use the given image(s) as references for video generation.").
- `generation_config.video_config.task` ∈ {`text_to_video`, `image_to_video`, `reference_to_video`, `edit`}. Files via `client.files.upload/get/download`.
- Editing: simple prompts + "Keep everything else the same" + one change per turn.
- ADK: `adk.Agent(model=, name=, instruction=, tools=[])`; `Runner` + session service; Python ≥3.10.

### Assumptions (change here if wrong)
- **App name:** OmniChain (matches working dir + reference [6]).
- **Auth:** single-tenant v1; Cloud Run guarded by IAM/IAP; backend uses a service account (ADC) for GCS/Firestore/genai. No end-user login in v1.
- **Storyboard/Compiler model:** `gemini-3.6-flash` (configurable via env; `gemini-3.1-pro` for higher-quality decomposition).
- **No Veo, ever.** No fallback path. All errors surface in the UI.

---

## Repository layout

```
omnichain/
├── README.md                       # omnimash-style banner/badges/subtitle (Task 1)
├── Dockerfile                      # multi-stage: build SPA → serve via FastAPI (Task 15)
├── docs/                           # exists; add plans/, notes/ already present
├── backend/
│   ├── pyproject.toml              # uv, ruff, ty, pytest (Task 2)
│   ├── src/omnichain/
│   │   ├── config.py               # pydantic-settings (Task 3)
│   │   ├── logging_config.py       # structured JSON logging + correlation id (Task 3)
│   │   ├── errors.py               # exception types + FastAPI handler (Task 4)
│   │   ├── main.py                 # app factory, middleware, static SPA mount (Task 4,15)
│   │   ├── models/schemas.py       # pydantic: Session, Shot, Character, prompts (Task 5)
│   │   ├── services/
│   │   │   ├── gcs_service.py      # bucket/folder browse, upload/download (Task 6)
│   │   │   ├── firestore_store.py  # sessions, shots, character library (Task 7)
│   │   │   ├── interactions.py     # google-genai Interactions wrapper (Task 9)
│   │   │   └── ffmpeg_service.py   # concat + audio mux/duck (Task 12)
│   │   ├── agents/
│   │   │   ├── storyboard_agent.py # ADK: vision → shots (Task 8)
│   │   │   └── prompt_compiler.py  # ADK: shot → 6-part prompt (Task 10)
│   │   ├── prompts/                # meta-prompt templates (Task 8,10)
│   │   └── api/                    # routers (Task 6,7,11,13)
│   └── tests/
└── frontend/                       # Vite + React + TS (Task 14)
```

---

## Backend tasks (TDD: uv/ruff/ty/pytest per CODE_STANDARDS.md; NO Co-Authored-By trailers)

Each task follows: write failing test → run/verify fail → minimal impl → run/verify pass → `uv run ruff format . && uv run ruff check --fix . && uv run ty check src/` → commit.

### Task 1: README + project skeleton
- Create `README.md` mirroring the omnimash layout: linked banner image (`<!-- TODO: banner -->` placeholder → `imgs/omnichain_banner.png`), `# 🎬 OmniChain 🪄`, a badges row (Python 3.12, uv, ruff, ty, Google ADK, Vertex AI, Gemini Omni Flash, FastAPI, Pytest), a `>` blockquote tagline naming Dripwarts + the tech stack, then a description paragraph of the pipeline. Add TODO for banner.
- Commit.

### Task 2: Backend bootstrap
- `cd backend && uv init --package omnichain`; `uv add fastapi uvicorn[standard] google-genai google-adk google-cloud-storage google-cloud-firestore pydantic-settings ffmpeg-python`; `uv add --group dev pytest pytest-asyncio ruff ty httpx`.
- Configure `pyproject.toml`: ruff `select=["ALL"]` w/ pragmatic ignores, `ty` env python 3.12, pytest addopts. Commit.

### Task 3: Config + structured logging
- **Test:** `Settings` loads `GCS_DEFAULT_BUCKET`, `GCP_PROJECT`, `STORYBOARD_MODEL`, `OMNI_MODEL` from env; logging emits JSON w/ a per-request `correlation_id`.
- Implement `config.py` (pydantic-settings) + `logging_config.py`. Commit.

### Task 4: Error model + FastAPI app factory
- **Test:** an endpoint raising `OmniChainError("...")` returns a structured JSON body `{error: {type, message, detail, correlation_id}}` with correct status; unexpected exceptions map to 500 with the same shape. Assert **no Veo/fallback** logic exists.
- Implement `errors.py` (base `OmniChainError`, subclasses: `GenerationError`, `GcsError`, `AgentError`), a global exception handler, and `main.py` app factory + correlation-id middleware. Commit.

### Task 5: Domain schemas
- **Test:** pydantic round-trips for `Character` (id, name, physical_traits, wardrobe, reference_uri, scope∈{global,session}), `Shot` (id, index, duration_s 3–10 validator, draft_text, compiled_prompt, interaction_id, versions[], status), `Session` (id, concept, style_tone, master_audio_uri, gcs_bucket, gcs_folder, character_ids[], shots[]).
- Implement `models/schemas.py`. Commit.

### Task 6: GCS service + browse endpoint
- **Test (mock `storage.Client`):** `list_folders(bucket)` returns top-level "subfolders" via delimiter-`/` prefixes; `upload_bytes`/`download_bytes`/`signed_url` behave; errors wrap into `GcsError`.
- Implement `gcs_service.py` + `api/gcs.py` (`GET /api/gcs/folders?bucket=`, `POST /api/gcs/folders`). This powers "enter bucket → see subfolders → pick/create folder". Commit.

### Task 7: Firestore store + session/character endpoints
- **Test (mock Firestore):** CRUD for sessions, shots, and the **global character library**; `attach_character(session, char_id)` copies a global char reference into the session.
- Implement `firestore_store.py` + `api/sessions.py`, `api/characters.py` (global list/create/update/delete + per-session attach/detach). Commit.

### Task 8: Storyboard Agent (vision → shots)
- **Test (mock ADK/genai):** given concept + style_tone + target_seconds, returns 3–6 `Shot` drafts, each `duration_s ≤ 10` and summing ≈ target; deterministic parsing of the agent's structured JSON output.
- Implement `agents/storyboard_agent.py` (ADK `Agent` w/ system instruction in `prompts/storyboard_system.md`: act as director, native storyboard beats, cap each shot <10s, output strict JSON schema). Add `POST /api/sessions/{id}/storyboard`. User can edit shot text before generate. Commit.

### Task 9: Interactions API wrapper (generation)
- **Test (mock `genai.Client`):** `generate_clip(compiled_prompt, reference_files, task)` calls `interactions.create` once, returns `(interaction_id, video_bytes)`; `edit_clip(previous_interaction_id, instruction)` passes `previous_interaction_id` and appends "Keep everything else the same"; every call wrapped in try/except → `GenerationError` surfaced with raw provider message + correlation id; **assert no Veo fallback**.
- Implement `services/interactions.py`: client init, base64 decode of `output_video.data`, file upload helper (`client.files.upload` for reference images / GCS URIs), request+response logging. Commit.

### Task 10: Prompt Compiler agent (Anchor & Inject)
- **Test (mock ADK):** raw shorthand → 6-part compiled string in exact order `[SUBJECT ANCHOR]+[AESTHETIC INJECTION]+[ENVIRONMENT]+[CAMERA/LIGHTING]+[MOTION]+[AUDIO]`; when a `Character` w/ `reference_uri` is attached, output injects the anchor traits **and** an explicit image-role declaration `[# References <IMAGE_REF_0>@<name>]` + guiding suffix, and sets `task=reference_to_video`; single-scene + duration cue included.
- Implement `agents/prompt_compiler.py` + `prompts/compiler_system.md` (the user's meta-prompt, corrected to "OmniChain", extended with the image-role rule and single-scene/duration rules). Commit.

### Task 11: Generation endpoint (per shot) + persistence
- **Test:** `POST /api/sessions/{id}/shots/{shot_id}/generate` → compiles prompt, calls interactions wrapper, saves mp4 to `gs://bucket/folder/sessions/{id}/shots/{shot_id}/clip_v1.mp4`, stores `interaction_id`+version in Firestore, returns signed URL. Errors surface, no fallback.
- Implement router. Commit.

### Task 12: FFmpeg assembly + audio mux
- **Test (mock subprocess/ffmpeg):** `concat(clip_paths)` builds a valid concat command; `mux_master_audio(video, audio)` **ducks/replaces** the native music bed with the master track (documented filter graph); no-audio path leaves native audio intact.
- Implement `ffmpeg_service.py`. Commit.

### Task 13: Editing + assembly endpoints
- **Test:** `POST .../shots/{shot_id}/edit` enforces one-change semantics (rejects/warns on multi-change heuristics), calls `edit_clip(previous_interaction_id, ...)`, saves `clip_v{n+1}.mp4`. `POST /api/sessions/{id}/assemble` concats approved clips, optional master overlay, writes `final/final_cut.mp4`, returns signed URL.
- Implement routers. Commit.

## Frontend tasks

### Task 14: React/Vite wizard
- `cd frontend && npm create vite@latest . -- --template react-ts`; add router + a data-fetch layer (TanStack Query) + a component lib (shadcn/ui or MUI).
- Four-stage wizard mapped to the API:
  1. **Vision** — concept textarea, Style/Tone field, optional audio upload, reference-image upload, **bucket input → subfolder browser** (Task 6), character library picker (Task 7).
  2. **Storyboard** — editable text cards for each shot (Task 8), "Generate".
  3. **Dailies** — side-by-side clip grid; click a clip → per-clip **chat** panel that enforces one-change-per-turn (Task 13); version history.
  4. **Final Cut** — assemble + preview + download (Task 13).
- Global error toast/banner surfacing backend `{error}` payloads (no silent failures). Commit incrementally.

### Task 15: Dockerize + Cloud Run
- Multi-stage `Dockerfile`: stage 1 `npm run build` → static assets; stage 2 `uv sync` + copy SPA into `backend/src/omnichain/static`, FastAPI mounts it; install `ffmpeg` in the image.
- `main.py` serves SPA + `/api/*`. Document `gcloud run deploy` + required env/roles (Storage Admin, Datastore User, Vertex/GenAI user) + service-account setup. Commit.

---

## Verification (end-to-end)

1. **Unit/type/lint:** `cd backend && uv run pytest && uv run ruff check . && uv run ty check src/` — all green.
2. **Local run:** `uv run uvicorn omnichain.main:app --reload` + `cd frontend && npm run dev`; walk the 4 stages against a **real GCS bucket** and **real** `gemini-omni-flash-preview` (no mocks) for one 30s concept (e.g. "Snape Dogg trap disstrack, gritty 90s rap video").
3. **Character path:** save a global character w/ a GCS reference image; confirm the compiled prompt contains the `[# References <IMAGE_REF_0>@...]` declaration and the clip preserves likeness (character-decay check).
4. **Edit path:** in Dailies, "Change the jacket to green" → confirm a new version via `previous_interaction_id` (not a full regen); try a multi-change message → confirm UI blocks it.
5. **Assembly + audio:** approve all clips, assemble; with and without a master track → confirm ducking vs native audio.
6. **Failure path:** force an API error (bad model id) → confirm it surfaces in the UI with correlation id and **no Veo fallback** runs.
7. **Deploy:** `gcloud run deploy`; repeat step 2 against the Cloud Run URL.

## Notes to capture in `docs/notes/` during build
- Exact Interactions API response shape once hit live (base64 vs uri; `store`/`background` behavior) — the docs were thin on the schema.
- The working image-role declaration syntax that actually preserves likeness.
- FFmpeg ducking filter graph that sounded best.
