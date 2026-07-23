"""Tests for application settings loading."""

from omnichain.config import Settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("PROJECT_ID", "my-proj")
    monkeypatch.setenv("GCS_BUCKET_NAME", "omnichain-media-${PROJECT_ID}")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "0")
    monkeypatch.setenv("GOOGLE_API_KEY", "abc-key")

    settings = Settings(_env_file=None)

    assert settings.project_id == "my-proj"
    # ${PROJECT_ID} placeholder is expanded from project_id
    assert settings.gcs_bucket_name == "omnichain-media-my-proj"
    assert settings.google_genai_use_vertexai is False
    # gemini_api_key falls back to google_api_key when unset
    assert settings.gemini_api_key == "abc-key"
    # google_cloud_project defaults to project_id
    assert settings.google_cloud_project == "my-proj"


def test_settings_have_model_defaults(monkeypatch):
    monkeypatch.setenv("PROJECT_ID", "p")
    settings = Settings(_env_file=None)
    assert settings.omni_model == "gemini-omni-flash-preview"
    assert settings.storyboard_model  # non-empty default
