"""Tests for application settings."""

import pytest

from tests.helpers import SettingsForTests


def test_settings_defaults() -> None:
    """Check fallback values when no environment variables are set."""

    s = SettingsForTests()
    assert s.database_url == "postgresql+psycopg://rag:rag@localhost:5432/rag"
    assert s.jwt_algorithm == "HS256"
    assert s.jwt_access_token_ttl_hours == 24


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that RAG_-prefixed variables override the defaults."""

    monkeypatch.setenv("RAG_DATABASE_URL", "postgresql+psycopg://u:p@h:1/db")
    monkeypatch.setenv("RAG_JWT_SECRET", "abc")
    s = SettingsForTests()
    assert s.database_url == "postgresql+psycopg://u:p@h:1/db"
    assert s.jwt_secret == "abc"
