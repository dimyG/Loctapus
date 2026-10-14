"""Application settings sourced from ``RAG_``-prefixed environment variables."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration; falls back to the defaults below when unset."""

    model_config = SettingsConfigDict(env_prefix="RAG_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://rag:rag@localhost:5432/rag"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_ttl_hours: int = 24
    environment: Literal["dev", "production"] = "dev"
    cors_origins: list[str] = ["http://localhost:5173"]

    broker_url: str = "amqp://guest:guest@localhost:5672//"
    s3_endpoint: str = "http://localhost:3900"
    s3_access_key: str = "rag-dev-key"
    s3_secret_key: str = "rag-dev-secret-local"
    # Must stay identical to s3_region in deploy/garage.toml, or Garage rejects signatures.
    s3_region: str = "garage"
    s3_bucket: str = "rag-dev"
    parser_provider: Literal["stub"] = "stub"
    embedding_provider: Literal["stub"] = "stub"
    chunk_target_tokens: int = 600
    chunk_max_tokens: int = 1000
    chunk_overlap_tokens: int = 80
    embedding_batch_size: int = 64
    outbox_poll_interval_seconds: float = 1.0
    outbox_batch_size: int = 20
    outbox_retry_base_seconds: float = 1.0
    outbox_retry_max_seconds: float = 300.0
    outbox_publish_timeout_seconds: float = 10.0
    max_upload_mb: int = 25

    @model_validator(mode="after")
    def _reject_default_secret_in_production(self) -> Self:
        """Reject the development JWT secret when running in production."""

        if self.environment == "production" and self.jwt_secret == "dev-secret-change-me":
            raise ValueError("jwt_secret must be set explicitly when environment is production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, creating them on first call."""

    return Settings()
