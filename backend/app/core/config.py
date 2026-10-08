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
