"""Request and response bodies for the source endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.ingestion.status import RunStatus


class SourceOut(BaseModel):
    """Source as returned by the API, with status and filename derived from its item."""

    id: UUID
    project_id: UUID
    type: str
    status: RunStatus
    filename: str
    created_at: datetime
