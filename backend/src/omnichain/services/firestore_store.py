"""Firestore-backed persistence for sessions and the character library.

Cloud Run is stateless, so all durable app metadata lives in Firestore.
Large binary assets (clips, references, audio) live in GCS; this store only
holds the JSON-serialisable document models.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from google.cloud import firestore

from omnichain.errors import NotFoundError
from omnichain.models.schemas import Character, CharacterScope, Session

if TYPE_CHECKING:
    from google.cloud.firestore import Client

logger = logging.getLogger("omnichain.firestore")

_SESSIONS = "sessions"
_CHARACTERS = "characters"


class FirestoreStore:
    """CRUD for sessions and characters over ``google-cloud-firestore``."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client if client is not None else firestore.Client()

    # -- sessions ---------------------------------------------------------

    def create_session(self, session: Session) -> Session:
        self._client.collection(_SESSIONS).document(session.id).set(session.model_dump(mode="json"))
        return session

    def get_session(self, session_id: str) -> Session:
        snap = self._client.collection(_SESSIONS).document(session_id).get()
        if not snap.exists:
            msg = f"Session '{session_id}' not found"
            raise NotFoundError(msg)
        return Session.model_validate(snap.to_dict())

    def list_sessions(self) -> list[Session]:
        return [
            Session.model_validate(s.to_dict()) for s in self._client.collection(_SESSIONS).stream()
        ]

    def update_session(self, session: Session) -> Session:
        self.get_session(session.id)  # ensure it exists
        self._client.collection(_SESSIONS).document(session.id).set(session.model_dump(mode="json"))
        return session

    def delete_session(self, session_id: str) -> None:
        self._client.collection(_SESSIONS).document(session_id).delete()

    # -- characters -------------------------------------------------------

    def create_character(self, character: Character) -> Character:
        self._client.collection(_CHARACTERS).document(character.id).set(
            character.model_dump(mode="json")
        )
        return character

    def get_character(self, character_id: str) -> Character:
        snap = self._client.collection(_CHARACTERS).document(character_id).get()
        if not snap.exists:
            msg = f"Character '{character_id}' not found"
            raise NotFoundError(msg)
        return Character.model_validate(snap.to_dict())

    def list_characters(self, scope: CharacterScope | None = None) -> list[Character]:
        chars = [
            Character.model_validate(c.to_dict())
            for c in self._client.collection(_CHARACTERS).stream()
        ]
        if scope is not None:
            chars = [c for c in chars if c.scope == scope]
        return chars

    def update_character(self, character: Character) -> Character:
        self.get_character(character.id)  # ensure it exists
        self._client.collection(_CHARACTERS).document(character.id).set(
            character.model_dump(mode="json")
        )
        return character

    def delete_character(self, character_id: str) -> None:
        self._client.collection(_CHARACTERS).document(character_id).delete()

    # -- attach / detach --------------------------------------------------

    def attach_character(self, session_id: str, character_id: str) -> Session:
        """Add a character reference to a session (idempotent)."""
        self.get_character(character_id)  # raises NotFoundError if missing
        session = self.get_session(session_id)
        if character_id not in session.character_ids:
            session.character_ids.append(character_id)
            self.update_session(session)
        return session

    def detach_character(self, session_id: str, character_id: str) -> Session:
        """Remove a character reference from a session (idempotent)."""
        session = self.get_session(session_id)
        if character_id in session.character_ids:
            session.character_ids.remove(character_id)
            self.update_session(session)
        return session


@lru_cache
def get_firestore_store() -> FirestoreStore:
    """FastAPI dependency returning a shared FirestoreStore."""
    return FirestoreStore()
