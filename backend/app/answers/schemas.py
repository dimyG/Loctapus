"""Request and response schemas for grounded answers."""

from pydantic import BaseModel, Field

from app.retrieval.schemas import QueryText, RetrievedChunkOut


class AnswerIn(BaseModel):
    """One answer request body: the query plus optional retrieval overrides."""

    query: QueryText
    top_k: int | None = Field(default=None, ge=1, le=50)
    rerank: bool = False
    max_chunks_per_document: int | None = Field(default=None, ge=1)


class AnswerOut(BaseModel):
    """One generated answer with the exact chunks that grounded it."""

    answer: str
    chunks: list[RetrievedChunkOut]
