"""Tests for the Firestore-backed store."""

import pytest

from omnichain.errors import NotFoundError
from omnichain.models.schemas import Character, CharacterScope, Session
from omnichain.services.firestore_store import FirestoreStore
from tests.fakes import FakeFirestore


def _store() -> FirestoreStore:
    return FirestoreStore(client=FakeFirestore())


def _session(**kw) -> Session:
    defaults = {
        "concept": "c",
        "style_tone": "t",
        "gcs_bucket": "b",
        "gcs_folder": "f",
    }
    return Session(**{**defaults, **kw})


def test_session_create_get_list_delete():
    store = _store()
    session = _session()
    store.create_session(session)

    assert store.get_session(session.id) == session
    assert [s.id for s in store.list_sessions()] == [session.id]

    store.delete_session(session.id)
    with pytest.raises(NotFoundError):
        store.get_session(session.id)


def test_get_missing_session_raises_not_found():
    with pytest.raises(NotFoundError):
        _store().get_session("nope")


def test_character_crud():
    store = _store()
    char = Character(name="Snape Dogg", physical_traits="gaunt, hooked nose")
    store.create_character(char)

    assert store.get_character(char.id) == char
    char.wardrobe = "puffer + chain"
    store.update_character(char)
    assert store.get_character(char.id).wardrobe == "puffer + chain"

    assert [c.id for c in store.list_characters()] == [char.id]
    store.delete_character(char.id)
    with pytest.raises(NotFoundError):
        store.get_character(char.id)


def test_list_characters_filters_by_scope():
    store = _store()
    g = Character(name="G", physical_traits="x", scope=CharacterScope.GLOBAL)
    s = Character(name="S", physical_traits="y", scope=CharacterScope.SESSION)
    store.create_character(g)
    store.create_character(s)
    globals_only = store.list_characters(scope=CharacterScope.GLOBAL)
    assert [c.id for c in globals_only] == [g.id]


def test_attach_character_adds_reference_once():
    store = _store()
    char = Character(name="Snape Dogg", physical_traits="gaunt")
    store.create_character(char)
    session = _session()
    store.create_session(session)

    updated = store.attach_character(session.id, char.id)
    assert updated.character_ids == [char.id]
    # idempotent
    updated = store.attach_character(session.id, char.id)
    assert updated.character_ids == [char.id]

    detached = store.detach_character(session.id, char.id)
    assert detached.character_ids == []


def test_attach_missing_character_raises():
    store = _store()
    session = _session()
    store.create_session(session)
    with pytest.raises(NotFoundError):
        store.attach_character(session.id, "ghost")
