"""Tests for application settings."""

import pytest
from pydantic import ValidationError

from tests.helpers import SettingsForTests


def test_settings_defaults() -> None:
    """Check fallback values when no environment variables are set."""

    s = SettingsForTests()
    assert s.database_url == "postgresql+psycopg://rag:rag@localhost:5432/rag"
    assert s.jwt_algorithm == "HS256"
    assert s.jwt_access_token_ttl_hours == 24
    assert s.environment == "dev"


def test_settings_env_override(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that RAG_-prefixed variables override the defaults."""

    monkeypatch.setenv("RAG_DATABASE_URL", "postgresql+psycopg://u:p@h:1/db")
    monkeypatch.setenv("RAG_JWT_SECRET", "abc")
    monkeypatch.setenv("RAG_ENVIRONMENT", "production")
    s = SettingsForTests()
    assert s.database_url == "postgresql+psycopg://u:p@h:1/db"
    assert s.jwt_secret == "abc"
    assert s.environment == "production"


def test_production_rejects_default_jwt_secret() -> None:
    """Check that production refuses to run with the development JWT secret."""

    with pytest.raises(ValidationError):
        SettingsForTests(environment="production")


def test_production_accepts_explicit_jwt_secret() -> None:
    """Check that production accepts an explicitly configured secret."""

    s = SettingsForTests(environment="production", jwt_secret="a-real-production-secret")
    assert s.environment == "production"


def test_cors_origins_default() -> None:
    """CORS defaults to the Vite dev origin."""

    assert SettingsForTests().cors_origins == ["http://localhost:5173"]


def test_cors_origins_env_json(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """RAG_CORS_ORIGINS parses as a JSON list of origins."""

    monkeypatch.setenv("RAG_CORS_ORIGINS", '["https://app.example.com"]')
    assert SettingsForTests().cors_origins == ["https://app.example.com"]
