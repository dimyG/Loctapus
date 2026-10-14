"""ORM model for the transactional outbox of domain events."""

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class OutboxEvent(Base):
    """A domain event committed inside its transaction and published at least once later."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        # The poller scans due unpublished rows, next attempt first; published rows and
        # backed-off rows leave the index.
        Index(
            "ix_outbox_events_next_attempt_at_unpublished",
            "next_attempt_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String)
    aggregate_type: Mapped[str] = mapped_column(String)
    aggregate_id: Mapped[UUID] = mapped_column()
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    # The dispatcher's due gate: a failed row waits one backoff interval before its next
    # attempt, so poison and failures cannot starve the rows behind them.
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_error: Mapped[str | None] = mapped_column(Text)
