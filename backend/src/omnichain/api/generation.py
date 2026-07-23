"""Per-shot video generation: compile -> generate -> store -> signed URL."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from omnichain.agents.prompt_compiler import PromptCompiler, get_prompt_compiler
from omnichain.errors import GenerationError, NotFoundError
from omnichain.models.schemas import Session, Shot, ShotStatus, ShotVersion
from omnichain.services.firestore_store import FirestoreStore, get_firestore_store
from omnichain.services.gcs_service import GcsService, get_gcs_service
from omnichain.services.interactions import InteractionsClient, get_interactions_client

logger = logging.getLogger("omnichain.generation")

router = APIRouter(prefix="/api/sessions", tags=["generation"])

StoreDep = Annotated[FirestoreStore, Depends(get_firestore_store)]
CompilerDep = Annotated[PromptCompiler, Depends(get_prompt_compiler)]
InteractionsDep = Annotated[InteractionsClient, Depends(get_interactions_client)]
GcsDep = Annotated[GcsService, Depends(get_gcs_service)]


class GenerateResponse(BaseModel):
    shot_id: str
    version: int
    interaction_id: str
    clip_uri: str
    signed_url: str | None
    status: ShotStatus


def _find_shot(session: Session, shot_id: str) -> Shot:
    for shot in session.shots:
        if shot.id == shot_id:
            return shot
    msg = f"Shot '{shot_id}' not found in session '{session.id}'"
    raise NotFoundError(msg)


def _clip_path(session: Session, shot_id: str, version: int) -> str:
    folder = session.gcs_folder.strip("/")
    return f"{folder}/sessions/{session.id}/shots/{shot_id}/clip_v{version}.mp4"


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
    if clip.video_bytes is not None:
        clip_uri = gcs.upload_bytes(
            session.gcs_bucket, path, clip.video_bytes, content_type="video/mp4"
        )
        signed_url = gcs.signed_url(session.gcs_bucket, path)
    elif clip.video_uri is not None:
        # Provider delivered a URI instead of inline bytes; reference it directly.
        clip_uri = clip.video_uri
        signed_url = None
    else:
        msg = "Generation returned neither video bytes nor a URI"
        raise GenerationError(msg)

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
