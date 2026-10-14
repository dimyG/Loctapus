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
    assert s.outbox_poll_interval_seconds == 1.0
    assert s.outbox_batch_size == 20
    assert s.outbox_retry_base_seconds == 1.0
    assert s.outbox_retry_max_seconds == 300.0
    assert s.outbox_publish_timeout_seconds == 10.0


def test_settings_env_override(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that RAG_-prefixed variables override the defaults."""

    monkeypatch.setenv("RAG_DATABASE_URL", "postgresql+psycopg://u:p@h:1/db")
    monkeypatch.setenv("RAG_JWT_SECRET", "abc")
    monkeypatch.setenv("RAG_S3_SECRET_KEY", "prod-s3-secret")
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

    s = SettingsForTests(
        environment="production",
        jwt_secret="a-real-production-secret",
        s3_secret_key="a-real-storage-secret",
    )
    assert s.environment == "production"


def test_unknown_provider_setting_is_rejected() -> None:
    """Check that settings construction rejects a provider the factories cannot resolve.

    The invalid values go through ``model_validate`` because the typed constructor
    signature itself refuses them: rejection at construction is the feature.
    """

    with pytest.raises(ValidationError):
        SettingsForTests.model_validate({"parser_provider": "nope"})
    with pytest.raises(ValidationError):
        SettingsForTests.model_validate({"embedding_provider": "nope"})


def test_chunk_budgets_must_be_ordered() -> None:
    """Check that the chunk budgets must satisfy 0 <= overlap < target <= max."""

    with pytest.raises(ValidationError):
        SettingsForTests(chunk_overlap_tokens=600, chunk_target_tokens=600)
    with pytest.raises(ValidationError):
        SettingsForTests(chunk_target_tokens=2000, chunk_max_tokens=1000)
    assert SettingsForTests(chunk_overlap_tokens=80).chunk_target_tokens == 600


def test_production_rejects_default_s3_secret() -> None:
    """Check that production refuses the development storage secret."""

    with pytest.raises(ValidationError):
        SettingsForTests(environment="production", jwt_secret="a-real-production-secret")
    s = SettingsForTests(
        environment="production",
        jwt_secret="a-real-production-secret",
        s3_secret_key="a-real-storage-secret",
    )
    assert s.s3_secret_key == "a-real-storage-secret"


def test_cors_origins_default() -> None:
    """CORS defaults to the Vite dev origin."""

    assert SettingsForTests().cors_origins == ["http://localhost:5173"]


def test_cors_origins_env_json(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """RAG_CORS_ORIGINS parses as a JSON list of origins."""

    monkeypatch.setenv("RAG_CORS_ORIGINS", '["https://app.example.com"]')
    assert SettingsForTests().cors_origins == ["https://app.example.com"]


def test_ingestion_settings_defaults() -> None:
    """The S3 pipeline settings default to the compose services and the stub providers."""

    s = SettingsForTests()
    assert s.broker_url == "amqp://guest:guest@localhost:5672//"
    assert s.s3_endpoint == "http://localhost:3900"
    assert s.s3_access_key == "rag-dev-key"
    assert s.s3_secret_key == "rag-dev-secret-local"
    assert s.s3_region == "garage"
    assert s.s3_bucket == "rag-dev"
    assert s.parser_provider == "stub"
    assert s.embedding_provider == "stub"
    assert s.chunk_target_tokens == 600
    assert s.chunk_max_tokens == 1000
    assert s.chunk_overlap_tokens == 80
    assert s.embedding_batch_size == 64
    assert s.outbox_poll_interval_seconds == 1.0
    assert s.outbox_batch_size == 20
    assert s.max_upload_mb == 25


def test_broker_url_env_override(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """RAG_BROKER_URL selects the pytest vhost."""

    monkeypatch.setenv("RAG_BROKER_URL", "amqp://guest:guest@localhost:5672/rag_test")
    assert SettingsForTests().broker_url == "amqp://guest:guest@localhost:5672/rag_test"
