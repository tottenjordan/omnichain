"""Cloud Storage access: folder browsing and asset upload/download."""

from __future__ import annotations

import logging
from datetime import timedelta
from functools import lru_cache
from typing import TYPE_CHECKING

from google.cloud import storage

from omnichain.errors import GcsError

if TYPE_CHECKING:
    from google.cloud.storage import Client

logger = logging.getLogger("omnichain.gcs")


class GcsService:
    """Thin wrapper over ``google-cloud-storage`` with typed errors."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client if client is not None else storage.Client()

    def list_folders(self, bucket_name: str) -> list[str]:
        """Return top-level "subfolders" of a bucket (via ``/`` delimiter)."""
        try:
            iterator = self._client.list_blobs(bucket_name, delimiter="/")
            list(iterator)  # consume the page so ``prefixes`` is populated
            prefixes = iterator.prefixes
        except Exception as exc:
            msg = f"Failed to list folders in bucket '{bucket_name}'"
            logger.warning(msg)
            raise GcsError(msg, detail=str(exc)) from exc
        return sorted(prefix.rstrip("/") for prefix in prefixes)

    def create_folder(self, bucket_name: str, folder: str) -> str:
        """Create a zero-byte marker so an empty "folder" is browsable."""
        name = folder.strip("/")
        self.upload_bytes(bucket_name, f"{name}/", b"", content_type="application/x-directory")
        return name

    def upload_bytes(
        self,
        bucket_name: str,
        path: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload bytes and return the ``gs://`` URI."""
        try:
            blob = self._client.bucket(bucket_name).blob(path)
            blob.upload_from_string(data, content_type=content_type)
        except Exception as exc:
            msg = f"Failed to upload to gs://{bucket_name}/{path}"
            raise GcsError(msg, detail=str(exc)) from exc
        return f"gs://{bucket_name}/{path}"

    def download_bytes(self, bucket_name: str, path: str) -> bytes:
        try:
            blob = self._client.bucket(bucket_name).blob(path)
            return blob.download_as_bytes()
        except Exception as exc:
            msg = f"Failed to download gs://{bucket_name}/{path}"
            raise GcsError(msg, detail=str(exc)) from exc

    def signed_url(self, bucket_name: str, path: str, *, minutes: int = 60) -> str:
        """Return a V4 signed GET URL for browser playback/download."""
        try:
            blob = self._client.bucket(bucket_name).blob(path)
            return blob.generate_signed_url(expiration=timedelta(minutes=minutes), version="v4")
        except Exception as exc:
            msg = f"Failed to sign URL for gs://{bucket_name}/{path}"
            raise GcsError(msg, detail=str(exc)) from exc


@lru_cache
def get_gcs_service() -> GcsService:
    """FastAPI dependency returning a shared GcsService."""
    return GcsService()
