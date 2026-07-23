"""In-memory test doubles shared across tests."""

from __future__ import annotations

from typing import Any


class _FakeSnap:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class _FakeDoc:
    def __init__(self, store: dict[str, dict[str, Any]], doc_id: str) -> None:
        self._store = store
        self._id = doc_id

    def set(self, data: dict[str, Any]) -> None:
        self._store[self._id] = data

    def get(self) -> _FakeSnap:
        return _FakeSnap(self._store.get(self._id))

    def delete(self) -> None:
        self._store.pop(self._id, None)


class _FakeCollection:
    def __init__(self, store: dict[str, dict[str, Any]]) -> None:
        self._store = store

    def document(self, doc_id: str) -> _FakeDoc:
        return _FakeDoc(self._store, doc_id)

    def stream(self) -> list[_FakeSnap]:
        return [_FakeSnap(v) for v in self._store.values()]


class FakeFirestore:
    """Minimal in-memory stand-in for ``google.cloud.firestore.Client``."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict[str, Any]]] = {}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self._data.setdefault(name, {}))
