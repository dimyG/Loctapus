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
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base
from app.ingestion.status import TERMINAL_RUN_STATUSES, RunStatus

# The check constraint expression is built from the one status vocabulary so the
# database and the code can never disagree about which statuses exist.
_STATUS_CHECK = "status IN (" + ", ".join(f"'{status.value}'" for status in RunStatus) + ")"
_TERMINAL_VALUES = ", ".join(f"'{status.value}'" for status in TERMINAL_RUN_STATUSES)


class Document(Base):
    """A normalized parsed document, fingerprinted by its canonical JSON hash."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("source_item_id", "content_hash"),
        # project_id is repeated down sources -> source_items -> documents -> chunks so
        # retrieval filters chunks by project without joins; the composite FK makes the
        # database reject any row whose project differs from its item's, so the tenant
        # boundary is enforced by Postgres rather than remembered by writers.
        ForeignKeyConstraint(
            ["source_item_id", "project_id"],
            ["source_items.id", "source_items.project_id"],
            ondelete="CASCADE",
            name="fk_documents_source_item_id_project_id",
        ),
        UniqueConstraint("id", "project_id", name="uq_documents_id_project_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_item_id: Mapped[UUID] = mapped_column()
    project_id: Mapped[UUID] = mapped_column()
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
        Index("ix_chunks_project_id", "project_id"),
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
        # project_id is repeated down sources -> source_items -> documents -> chunks so
        # retrieval filters chunks by project without joins; the composite FK makes the
        # database reject any row whose project differs from its document's, so the
        # tenant boundary is enforced by Postgres rather than remembered by writers.
        ForeignKeyConstraint(
            ["document_id", "project_id"],
            ["documents.id", "documents.project_id"],
            ondelete="CASCADE",
            name="fk_chunks_document_id_project_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[UUID] = mapped_column()
    document_id: Mapped[UUID] = mapped_column()
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
        CheckConstraint(_STATUS_CHECK),
        # finished_at must exist exactly when the run reached a terminal status, so a
        # finished run is never mistaken for one still in flight and vice versa.
        CheckConstraint(f"(status IN ({_TERMINAL_VALUES})) = (finished_at IS NOT NULL)"),
        Index("ix_ingestion_runs_document_id", "document_id"),
        Index("ix_ingestion_runs_source_item_id_created_at_id", "source_item_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_item_id: Mapped[UUID] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"))
    # SET NULL keeps run history when a re-upload replaces the document.
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String)
    # The file version the run was created for: the worker fetches by this key and
    # verifies the fetched bytes against this hash, so a newer item version never
    # redirects a queued run.
    raw_object_key: Mapped[str] = mapped_column(String)
    content_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
