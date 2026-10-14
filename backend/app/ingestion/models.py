"""ORM models for normalized documents, chunks, and ingestion run history."""

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class Document(Base):
    """A normalized parsed document, fingerprinted by its canonical JSON hash."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("source_item_id", "content_hash"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_item_id: Mapped[UUID] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"))
    content_hash: Mapped[str] = mapped_column(String)
    raw_object_key: Mapped[str] = mapped_column(String)
    normalized_content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    """A retrieval-sized piece of one document, full-text searchable before embeddings land."""

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "position"),
        CheckConstraint("chunk_type IN ('text')"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Intentional denormalization for the retrieval hot path: chunk queries filter by
    # project without joining documents -> source_items -> sources.
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    heading_path: Mapped[list[str]] = mapped_column(JSONB)
    chunk_type: Mapped[str] = mapped_column(String)
    # metadata is reserved on SQLAlchemy declarative models, so the attribute is renamed;
    # the column keeps the SQL name metadata, which S4's retrieval SQL queries.
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
    content_hash: Mapped[str] = mapped_column(String)
    # 384 is the literal STUB_EMBEDDING_DIM; changing it requires an Alembic migration
    # re-typing this column and re-embedding every stored chunk.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384))
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', text)", persisted=True),
    )


class IngestionRun(Base):
    """One ingestion attempt for a source item, carrying the only stored status."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'fetching', 'processing', 'indexing', 'ready', 'failed')"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_item_id: Mapped[UUID] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"))
    # SET NULL keeps run history when a re-upload replaces the document.
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
