"""Per-shot video generation, conversational edits, and final assembly."""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from omnichain.agents.prompt_compiler import PromptCompiler, get_prompt_compiler
from omnichain.errors import (
    AssemblyError,
    ConflictError,
    GenerationError,
    NotFoundError,
    OneChangePerTurnError,
)
from omnichain.models.schemas import Session, Shot, ShotStatus, ShotVersion
from omnichain.services.ffmpeg_service import FfmpegService, get_ffmpeg_service
from omnichain.services.firestore_store import FirestoreStore, get_firestore_store
from omnichain.services.gcs_service import GcsService, get_gcs_service
from omnichain.services.interactions import (
    GeneratedClip,
    InteractionsClient,
    get_interactions_client,
)

logger = logging.getLogger("omnichain.generation")

router = APIRouter(prefix="/api/sessions", tags=["generation"])

StoreDep = Annotated[FirestoreStore, Depends(get_firestore_store)]
CompilerDep = Annotated[PromptCompiler, Depends(get_prompt_compiler)]
InteractionsDep = Annotated[InteractionsClient, Depends(get_interactions_client)]
GcsDep = Annotated[GcsService, Depends(get_gcs_service)]
FfmpegDep = Annotated[FfmpegService, Depends(get_ffmpeg_service)]

# Connectives that signal an edit is bundling more than one change. Bare " and "
# is included but only clauses of >= _MIN_CLAUSE_WORDS count, so adjective pairs
# ("dark and moody") pass while separate directives are caught.
_CHANGE_CONNECTORS = re.compile(
    r"\s+and then\s+|\s+then\s+|\s+also\s+|\s+as well as\s+|\s+plus\s+|;|\s+and\s+",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"[.!?]+")
_MIN_CLAUSE_WORDS = 3


class GenerateResponse(BaseModel):
    shot_id: str
    version: int
    interaction_id: str
    clip_uri: str
    signed_url: str | None
    status: ShotStatus


class EditRequest(BaseModel):
    instruction: str


class AssembleResponse(BaseModel):
    final_uri: str
    signed_url: str
    shot_count: int


def _find_shot(session: Session, shot_id: str) -> Shot:
    for shot in session.shots:
        if shot.id == shot_id:
            return shot
    msg = f"Shot '{shot_id}' not found in session '{session.id}'"
    raise NotFoundError(msg)


def _clip_path(session: Session, shot_id: str, version: int) -> str:
    folder = session.gcs_folder.strip("/")
    return f"{folder}/sessions/{session.id}/shots/{shot_id}/clip_v{version}.mp4"


def _parse_gs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        msg = f"Cannot assemble a non-GCS clip URI: '{uri}'"
        raise AssemblyError(msg)
    bucket, _, path = uri[len("gs://") :].partition("/")
    if not bucket or not path:
        msg = f"Malformed gs:// URI: '{uri}'"
        raise AssemblyError(msg)
    return bucket, path


def _enforce_one_change(instruction: str) -> None:
    """Reject an edit that clearly bundles multiple changes (one per turn)."""
    text = instruction.strip()
    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    clauses = [
        c for c in _CHANGE_CONNECTORS.split(text.rstrip(".")) if len(c.split()) >= _MIN_CLAUSE_WORDS
    ]
    if len(sentences) > 1 or len(clauses) > 1:
        msg = "Only one change per edit is allowed. Split this into separate edits."
        raise OneChangePerTurnError(msg, detail=instruction)


def _persist_clip(
    gcs: GcsService,
    session: Session,
    clip: GeneratedClip,
    path: str,
) -> tuple[str, str | None]:
    """Store a generated clip: upload inline bytes or reference a provider URI."""
    if clip.video_bytes is not None:
        clip_uri = gcs.upload_bytes(
            session.gcs_bucket, path, clip.video_bytes, content_type="video/mp4"
        )
        return clip_uri, gcs.signed_url(session.gcs_bucket, path)
    if clip.video_uri is not None:
        # Provider delivered a URI instead of inline bytes; reference it directly.
        return clip.video_uri, None
    msg = "Generation returned neither video bytes nor a URI"
    raise GenerationError(msg)


@router.post("/{session_id}/shots/{shot_id}/generate", response_model=GenerateResponse)
async def generate_shot(
    session_id: str,
    shot_id: str,
    store: StoreDep,
    compiler: CompilerDep,
    interactions: InteractionsDep,
    gcs: GcsDep,
) -> GenerateResponse:
    session = store.get_session(session_id)
    shot = _find_shot(session, shot_id)
    characters = [store.get_character(cid) for cid in session.character_ids]

    compiled = await compiler.compile(
        shot_draft=shot.draft_text,
        style_tone=session.style_tone,
        duration_s=shot.duration_s,
        characters=characters,
    )
    shot.compiled_prompt = compiled.text
    shot.status = ShotStatus.COMPILED

    clip = interactions.generate_clip(
        compiled.text,
        duration_s=shot.duration_s,
        reference_uris=compiled.reference_uris,
    )

    version = len(shot.versions) + 1
    path = _clip_path(session, shot_id, version)
    clip_uri, signed_url = _persist_clip(gcs, session, clip, path)

    shot.versions.append(
        ShotVersion(version=version, interaction_id=clip.interaction_id, clip_uri=clip_uri)
    )
    shot.interaction_id = clip.interaction_id
    shot.status = ShotStatus.GENERATED
    store.update_session(session)

    logger.info(
        "shot_generated",
        extra={"session_id": session_id, "shot_id": shot_id, "version": version},
    )
    return GenerateResponse(
        shot_id=shot_id,
        version=version,
        interaction_id=clip.interaction_id,
        clip_uri=clip_uri,
        signed_url=signed_url,
        status=shot.status,
    )


@router.post("/{session_id}/shots/{shot_id}/edit", response_model=GenerateResponse)
async def edit_shot(
    session_id: str,
    shot_id: str,
    req: EditRequest,
    store: StoreDep,
    interactions: InteractionsDep,
    gcs: GcsDep,
) -> GenerateResponse:
    session = store.get_session(session_id)
    shot = _find_shot(session, shot_id)
    if shot.interaction_id is None or not shot.versions:
        msg = f"Shot '{shot_id}' has not been generated yet; nothing to edit"
        raise ConflictError(msg)
    _enforce_one_change(req.instruction)

    clip = interactions.edit_clip(shot.interaction_id, req.instruction, duration_s=shot.duration_s)

    version = len(shot.versions) + 1
    path = _clip_path(session, shot_id, version)
    clip_uri, signed_url = _persist_clip(gcs, session, clip, path)

    shot.versions.append(
        ShotVersion(
            version=version,
            interaction_id=clip.interaction_id,
            clip_uri=clip_uri,
            instruction=req.instruction,
        )
    )
    shot.interaction_id = clip.interaction_id
    shot.status = ShotStatus.GENERATED
    store.update_session(session)

    logger.info(
        "shot_edited",
        extra={"session_id": session_id, "shot_id": shot_id, "version": version},
    )
    return GenerateResponse(
        shot_id=shot_id,
        version=version,
        interaction_id=clip.interaction_id,
        clip_uri=clip_uri,
        signed_url=signed_url,
        status=shot.status,
    )


@router.post("/{session_id}/shots/{shot_id}/approve", response_model=GenerateResponse)
def approve_shot(session_id: str, shot_id: str, store: StoreDep) -> GenerateResponse:
    session = store.get_session(session_id)
    shot = _find_shot(session, shot_id)
    if not shot.versions:
        msg = f"Shot '{shot_id}' has no generated clip to approve"
        raise ConflictError(msg)
    shot.status = ShotStatus.APPROVED
    store.update_session(session)
    latest = shot.versions[-1]
    return GenerateResponse(
        shot_id=shot_id,
        version=latest.version,
        interaction_id=latest.interaction_id,
        clip_uri=latest.clip_uri,
        signed_url=None,
        status=shot.status,
    )


@router.post("/{session_id}/assemble", response_model=AssembleResponse)
def assemble_session(
    session_id: str,
    store: StoreDep,
    gcs: GcsDep,
    ffmpeg: FfmpegDep,
) -> AssembleResponse:
    session = store.get_session(session_id)
    approved = [
        shot
        for shot in sorted(session.shots, key=lambda s: s.index)
        if shot.status == ShotStatus.APPROVED and shot.versions
    ]
    if not approved:
        msg = "No approved shots to assemble; approve at least one clip first"
        raise AssemblyError(msg)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        clip_paths: list[str] = []
        for shot in approved:
            bucket, path = _parse_gs_uri(shot.versions[-1].clip_uri)
            local = tmpdir / f"shot_{shot.index:03d}.mp4"
            local.write_bytes(gcs.download_bytes(bucket, path))
            clip_paths.append(str(local))

        master_local: str | None = None
        if session.master_audio_uri:
            m_bucket, m_path = _parse_gs_uri(session.master_audio_uri)
            master_file = tmpdir / "master_audio"
            master_file.write_bytes(gcs.download_bytes(m_bucket, m_path))
            master_local = str(master_file)

        output_local = str(tmpdir / "final_cut.mp4")
        ffmpeg.assemble(clip_paths, output_local, master_audio=master_local)
        final_bytes = Path(output_local).read_bytes()

    folder = session.gcs_folder.strip("/")
    final_path = f"{folder}/sessions/{session.id}/final/final_cut.mp4"
    final_uri = gcs.upload_bytes(
        session.gcs_bucket, final_path, final_bytes, content_type="video/mp4"
    )
    signed_url = gcs.signed_url(session.gcs_bucket, final_path)

    logger.info(
        "session_assembled",
        extra={"session_id": session_id, "shot_count": len(approved)},
    )
    return AssembleResponse(final_uri=final_uri, signed_url=signed_url, shot_count=len(approved))
