"""Request and response schemas for retrieval."""

from typing import Annotated, Final
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

MAX_QUERY_CHARS: Final = 2000


# Pydantic's AfterValidator calls the value positionally; keyword-only is impossible here.
def _reject_nul(value: str) -> str:  # noqa: PLR0917
    """Reject NUL bytes, which Postgres text parameters cannot carry."""

    if "\x00" in value:
        raise ValueError("query must not contain NUL bytes")
    return value


# The query contract both /retrieve and /answer share: strip, then bound, then reject NULs,
# so the cap counts the stripped query and whitespace-only queries fail on min_length.
QueryText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUERY_CHARS),
    AfterValidator(_reject_nul),
]


class RetrieveIn(BaseModel):
    """One retrieval request body."""

    query: QueryText
    top_k: int = Field(default=10, ge=1, le=50)
    # Accepted and ignored until the S6 reranker lands; logged so history stays honest.
    rerank: bool = False
    # The S5 answer round resolves an omitted cap against answer_max_chunks_per_document;
    # a direct /retrieve request stays unbounded by default.
    max_chunks_per_document: int | None = Field(default=None, ge=1)


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
