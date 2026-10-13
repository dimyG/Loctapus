"""ORM models for sources and their uploaded content versions."""

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base

# The projects table is a string-named FK target here, and the worker imports
# only this module's chain (never the API routers), so it must load with us.
from app.projects import models as projects_models  # noqa: F401


class Source(Base):
    """A project's content source; this slice creates upload sources only."""

    __tablename__ = "sources"
    __table_args__ = (CheckConstraint("type IN ('upload')"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceItem(Base):
    """One uploaded content version, fingerprinted by the raw bytes' sha256 hash."""

    __tablename__ = "source_items"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String)
    filename: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String)
    raw_object_key: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
