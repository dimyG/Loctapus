"""ORM model for per-query retrieval logs."""

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class QueryLog(Base):
    """One logged retrieval query: request echo, per-stage candidates, and latency."""

    __tablename__ = "query_logs"
    __table_args__ = (
        # The per-project log tail: recency per project without scanning other tenants.
        Index("ix_query_logs_project_id_created_at", "project_id", "created_at"),
        Index("ix_query_logs_user_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    # No ON DELETE action: the user row owns its log history, and deleting a user does
    # not rewrite the project's query past.
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    query: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    latency_ms: Mapped[int] = mapped_column(Integer)
    stages: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
