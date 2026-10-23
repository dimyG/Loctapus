"""ORM models for per-user project conversations and their evidence snapshots."""

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class Conversation(Base):
    """One persisted conversation: a user's chat history inside one project."""

    __tablename__ = "conversations"
    __table_args__ = (
        # The latest-conversation lookup sorts per project and user, never across tenants.
        Index(
            "ix_conversations_project_id_user_id_last_message_at",
            "project_id",
            "user_id",
            "last_message_at",
        ),
        Index("ix_conversations_user_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    # No ON DELETE action: the user row owns its conversation history, and deleting a
    # user does not rewrite the project's chat past.
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Non-null from creation (server now()) so the latest lookup never sorts nulls.
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationMessage(Base):
    """One user or assistant message at one position inside one conversation."""

    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "position"),
        CheckConstraint("role IN ('user', 'assistant')"),
        # The route marks the router's path; it exists exactly on assistant messages.
        CheckConstraint("(role = 'user') = (route IS NULL)"),
        CheckConstraint("route IN ('direct', 'reuse', 'retrieve')"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    route: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationMessageChunk(Base):
    """The durable evidence snapshot that grounded one assistant message."""

    __tablename__ = "conversation_message_chunks"
    __table_args__ = (
        UniqueConstraint("message_id", "ordinal"),
        Index("ix_conversation_message_chunks_chunk_id", "chunk_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[UUID] = mapped_column(ForeignKey("conversation_messages.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    # Staleness is known and deferred (spec decision 8): re-ingestion replaces chunk
    # rows, so filename/heading_path/text/document_content_hash below are the durable
    # citation and chunk_id only links while the original row lives (hence SET NULL).
    chunk_id: Mapped[UUID | None] = mapped_column(ForeignKey("chunks.id", ondelete="SET NULL"))
    filename: Mapped[str] = mapped_column(Text)
    heading_path: Mapped[list[str]] = mapped_column(JSONB)
    text: Mapped[str] = mapped_column(Text)
    document_content_hash: Mapped[str] = mapped_column(Text)
