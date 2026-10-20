"""Application settings sourced from ``RAG_``-prefixed environment variables."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator
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
    llm_provider: Literal["stub", "groq"] = "stub"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-20b"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_tokens: int = Field(default=1024, gt=0)
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
    # Both feed RRF fusion: the legs' candidate budget and the rank-smoothing constant.
    retrieval_candidates_per_retriever: int = Field(default=50, gt=0)
    rrf_k: int = Field(default=60, gt=0)
    # The S5 answer round resolves a request's omitted top_k and per-document cap against these.
    answer_context_chunks: int = Field(default=10, ge=1, le=50)
    answer_max_chunks_per_document: int = Field(default=3, ge=1)

    @model_validator(mode="after")
    def _validate_chunk_budgets(self) -> Self:
        """Reject chunk budgets that would make the chunker miss or overlap wrongly.

        The packer assumes 0 <= overlap < target <= max; anything else either packs
        nothing per pass or lets a chunk exceed the max the embedding budget counts on.
        """

        if not (0 <= self.chunk_overlap_tokens < self.chunk_target_tokens <= self.chunk_max_tokens):
            raise ValueError(
                "chunk budgets must satisfy "
                "0 <= chunk_overlap_tokens < chunk_target_tokens <= chunk_max_tokens"
            )
        return self

    @model_validator(mode="after")
    def _reject_default_secret_in_production(self) -> Self:
        """Reject the development secrets when running in production."""

        if self.environment == "production" and self.jwt_secret == "dev-secret-change-me":
            raise ValueError("jwt_secret must be set explicitly when environment is production")
        if self.environment == "production" and self.s3_secret_key == "rag-dev-secret-local":
            raise ValueError("s3_secret_key must be set explicitly when environment is production")
        return self

    @model_validator(mode="after")
    def _require_groq_key(self) -> Self:
        """Reject an empty Groq key when the groq provider is selected."""

        if self.llm_provider == "groq" and not self.groq_api_key:
            raise ValueError("groq_api_key must be set when llm_provider is groq")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, creating them on first call."""

    return Settings()
