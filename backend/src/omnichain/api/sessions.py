"""Endpoints for creating and managing video-project sessions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from omnichain.models.schemas import Session
from omnichain.services.firestore_store import FirestoreStore, get_firestore_store

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

StoreDep = Annotated[FirestoreStore, Depends(get_firestore_store)]


class SessionCreate(BaseModel):
    concept: str
    style_tone: str
    gcs_bucket: str
    gcs_folder: str
    master_audio_uri: str | None = None
    character_ids: list[str] | None = None


@router.post("", status_code=201, response_model=Session)
def create_session(req: SessionCreate, store: StoreDep) -> Session:
    session = Session(
        concept=req.concept,
        style_tone=req.style_tone,
        gcs_bucket=req.gcs_bucket,
        gcs_folder=req.gcs_folder,
        master_audio_uri=req.master_audio_uri,
        character_ids=req.character_ids or [],
    )
    return store.create_session(session)


@router.get("", response_model=list[Session])
def list_sessions(store: StoreDep) -> list[Session]:
    return store.list_sessions()


@router.get("/{session_id}", response_model=Session)
def get_session(session_id: str, store: StoreDep) -> Session:
    return store.get_session(session_id)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str, store: StoreDep) -> Response:
    store.delete_session(session_id)
    return Response(status_code=204)


@router.post("/{session_id}/characters/{character_id}", response_model=Session)
def attach_character(session_id: str, character_id: str, store: StoreDep) -> Session:
    return store.attach_character(session_id, character_id)


@router.delete("/{session_id}/characters/{character_id}", response_model=Session)
def detach_character(session_id: str, character_id: str, store: StoreDep) -> Session:
    return store.detach_character(session_id, character_id)
