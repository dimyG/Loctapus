"""ORM model for the transactional outbox of domain events."""

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class OutboxEvent(Base):
    """A domain event committed inside its transaction and published at least once later."""

    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String)
    aggregate_type: Mapped[str] = mapped_column(String)
    aggregate_id: Mapped[UUID] = mapped_column()
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
