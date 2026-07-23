# google-genai Interactions API (as installed, v2.14.0)

What the SDK actually exposes for `gemini-omni-flash-preview` video generation,
discovered 2026-07-23 by reading the installed package (the public docs were
thin). Re-verify against a **live** call — none of this has been hit against the
real API yet; all backend tests mock `client.interactions.create`.

## Access path

- `client.interactions` → `GeminiNextGenInteractions` (sync) /
  `AsyncGeminiNextGenInteractions` (via `client.aio`). Source lives in
  `google/genai/_gaos/google_genai.py`.
- `client.interactions.create(**body)` returns an `interactions.Interaction`.
  There is **no** `Interactions` symbol to import from `google.genai.interactions`;
  the module holds the pydantic types instead (see below).

## create() body keys (from `CreateModelInteraction.model_fields`)

`model`, `input`, `stream`, `store`, `background`, `system_instruction`,
`tools`, `response_modalities`, `response_mime_type`, `previous_interaction_id`,
`service_tier`, `webhook_config`, `response_format`, `environment`,
`generation_config`, `safety_settings`, `labels`.

- Unknown top-level keys raise `TypeError`; extra request fields must go through
  `extra_body=`.
- **`model` is a `Literal`** of specific ids (e.g. `gemini-2.5-flash`, ...). If
  `gemini-omni-flash-preview` is rejected by pydantic validation, fall back to
  `extra_body`/`request=`. **Verify live.**
- `input`: a list of content blocks. A bare content list (blocks WITHOUT a
  `role`/`content`/step-`type` key) is auto-wrapped into
  `[{"type": "user_input", "content": [...]}]` by `_normalize_create_body`.
  We pass `[{"type": "text", "text": ...}, {"type": "image", "uri": ...}]`.
- `generation_config.video_config.task` ∈ `text_to_video`, `image_to_video`,
  `reference_to_video`, `edit` (confirmed via `VideoConfig` + `UnrecognizedStr`).
- `response_format` for video: `VideoResponseFormat` has `type` (`"video"`),
  `duration` (e.g. `"8s"`), `aspect_ratio`, `delivery` (`"inline"|"uri"`),
  `gcs_uri`. We send `duration` here — **confirm this is where the 3–10s cap is
  read**, not elsewhere.

## Response shape

- `Interaction.id` → the interaction id used for `previous_interaction_id`.
- The SDK post-processes the response with `_add_output_properties_if_interaction`,
  which walks `steps[].content[]` and attaches `output_text` / `output_image` /
  `output_audio` / `output_video` convenience attrs.
- `output_video` is a `VideoContent`: `.data` (base64 str), `.uri`, `.mime_type`,
  `.resolution`, `.type`. With `delivery="inline"` expect `.data`; with `"uri"`
  expect `.uri` (likely a GCS/file URI). Our wrapper base64-decodes `.data` and
  otherwise returns `.uri`.

## Our wrapper

`services/interactions.py` → `InteractionsClient.generate_clip` /
`edit_clip` → returns `GeneratedClip(interaction_id, video_bytes, video_uri,
mime_type)`. No fallback: any exception becomes `GenerationError` with the raw
provider message in `.detail`. Edits append `"Keep everything else the same."`
and set `task="edit"` + `previous_interaction_id`.

Related: [[environment]] (genai auth mode), [[README]] (notes index).
