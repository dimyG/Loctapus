"""ORM models for sources and their uploaded content versions."""

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class Source(Base):
    """A project's content source; this slice creates upload sources only."""

    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("type IN ('upload')"),
        Index("ix_sources_project_id", "project_id"),
        # Exists only as the unique target the composite FK on source_items requires.
        UniqueConstraint("id", "project_id", name="uq_sources_id_project_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceItem(Base):
    """One uploaded content version, fingerprinted by the raw bytes' sha256 hash."""

    __tablename__ = "source_items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        CheckConstraint("size_bytes > 0"),
        # project_id is repeated down sources -> source_items -> documents -> chunks so
        # retrieval filters chunks by project without joins; the composite FK makes the
        # database reject any row whose project differs from its source's, so the tenant
        # boundary is enforced by Postgres rather than remembered by writers.
        ForeignKeyConstraint(
            ["source_id", "project_id"],
            ["sources.id", "sources.project_id"],
            ondelete="CASCADE",
            name="fk_source_items_source_id_project_id",
        ),
        UniqueConstraint("id", "project_id", name="uq_source_items_id_project_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[UUID] = mapped_column()
    project_id: Mapped[UUID] = mapped_column()
    external_id: Mapped[str] = mapped_column(String)
    filename: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String)
    raw_object_key: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
