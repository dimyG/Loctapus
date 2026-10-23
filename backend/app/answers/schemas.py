"""Request and response schemas for grounded answers."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.conversations.schemas import SnapshotChunkOut
from app.retrieval.schemas import QueryText


class AnswerIn(BaseModel):
    """One answer request body: the query plus optional retrieval overrides."""

    query: QueryText
    top_k: int | None = Field(default=None, ge=1, le=50)
    rerank: bool = False
    max_chunks_per_document: int | None = Field(default=None, ge=1)
    # Null only before the client hydrates its latest conversation (S6 decision 15).
    conversation_id: UUID | None = None


class AnswerOut(BaseModel):
    """One generated answer with the exact snapshots that grounded it."""

    answer: str
    route: Literal["direct", "reuse", "retrieve"]
    conversation_id: UUID
    chunks: list[SnapshotChunkOut]
