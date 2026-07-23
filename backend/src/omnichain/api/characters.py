"""Endpoints for the reusable character library."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from omnichain.models.schemas import Character, CharacterScope
from omnichain.services.firestore_store import FirestoreStore, get_firestore_store

router = APIRouter(prefix="/api/characters", tags=["characters"])

StoreDep = Annotated[FirestoreStore, Depends(get_firestore_store)]


class CharacterCreate(BaseModel):
    name: str
    physical_traits: str
    wardrobe: str | None = None
    reference_uri: str | None = None
    scope: CharacterScope = CharacterScope.GLOBAL


@router.post("", status_code=201, response_model=Character)
def create_character(req: CharacterCreate, store: StoreDep) -> Character:
    character = Character(
        name=req.name,
        physical_traits=req.physical_traits,
        wardrobe=req.wardrobe,
        reference_uri=req.reference_uri,
        scope=req.scope,
    )
    return store.create_character(character)


@router.get("", response_model=list[Character])
def list_characters(store: StoreDep, scope: CharacterScope | None = None) -> list[Character]:
    return store.list_characters(scope=scope)


@router.get("/{character_id}", response_model=Character)
def get_character(character_id: str, store: StoreDep) -> Character:
    return store.get_character(character_id)


@router.put("/{character_id}", response_model=Character)
def update_character(character_id: str, character: Character, store: StoreDep) -> Character:
    character.id = character_id
    return store.update_character(character)


@router.delete("/{character_id}", status_code=204)
def delete_character(character_id: str, store: StoreDep) -> Response:
    store.delete_character(character_id)
    return Response(status_code=204)
