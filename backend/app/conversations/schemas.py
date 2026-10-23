"""Response schemas for the conversations endpoints."""

from uuid import UUID

from pydantic import BaseModel


class SnapshotChunkOut(BaseModel):
    """One persisted evidence snapshot as served by the API."""

    chunk_id: UUID | None
    filename: str
    heading_path: list[str]
    text: str
    document_content_hash: str


class MessageOut(BaseModel):
    """One conversation message with its evidence snapshots."""

    role: str
    content: str
    route: str | None
    chunks: list[SnapshotChunkOut]


class ConversationCreatedOut(BaseModel):
    """The 201 body of POST /conversations."""

    conversation_id: UUID


class LatestConversationOut(BaseModel):
    """The caller's latest conversation with its full message history."""

    conversation_id: UUID
    messages: list[MessageOut]
