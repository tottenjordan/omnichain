"""Application settings loaded from environment / .env files."""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for OmniChain.

    Values are read (case-insensitively) from environment variables, falling
    back to a local ``.env`` at the backend dir or repo root for development.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # GCP
    project_id: str = "hybrid-vertex"
    google_cloud_project: str = ""
    google_cloud_project_number: str = ""
    gcp_region: str = "us-central1"
    google_cloud_location: str = "global"

    # genai routing / auth
    google_genai_use_vertexai: bool = False
    google_api_key: str = ""
    gemini_api_key: str = ""

    # storage
    gcs_bucket_name: str = ""

    # models
    storyboard_model: str = "gemini-3.6-flash"
    omni_model: str = "gemini-omni-flash-preview"

    @model_validator(mode="after")
    def _resolve_placeholders(self) -> Settings:
        # Expand ${PROJECT_ID}-style placeholders used in the sample .env.
        if "${PROJECT_ID}" in self.gcs_bucket_name:
            self.gcs_bucket_name = self.gcs_bucket_name.replace("${PROJECT_ID}", self.project_id)
        if not self.google_cloud_project:
            self.google_cloud_project = self.project_id
        if not self.gemini_api_key and self.google_api_key:
            self.gemini_api_key = self.google_api_key
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance for dependency injection."""
    return Settings()
