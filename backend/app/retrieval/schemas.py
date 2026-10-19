"""Request and response schemas for retrieval."""

from typing import Annotated, Final
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, field_validator

MAX_QUERY_CHARS: Final = 2000


class RetrieveIn(BaseModel):
    """One retrieval request body."""

    # Stripping runs in the core schema before the length bounds, so the cap counts
    # the stripped query and whitespace-only queries fail on min_length directly.
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUERY_CHARS)]
    top_k: int = Field(default=10, ge=1, le=50)
    # Accepted and ignored until the S6 reranker lands; logged so history stays honest.
    rerank: bool = False
    # The product default is chosen at the S5 chat round; null means unbounded.
    max_chunks_per_document: int | None = Field(default=None, ge=1)

    # Pydantic calls validators with a positional value; keyword-only would be rejected.
    @field_validator("query")
    @classmethod
    def _reject_nul(cls, value: str) -> str:  # noqa: PLR0917
        """Reject NUL bytes, which Postgres text parameters cannot carry."""

        if "\x00" in value:
            raise ValueError("query must not contain NUL bytes")
        return value


class RetrievedChunkOut(BaseModel):
    """One final retrieval result as served by the API."""

    id: UUID
    document_id: UUID
    source_item_id: UUID
    filename: str
    position: int
    heading_path: list[str]
    chunk_type: str
    text: str
    score: float
