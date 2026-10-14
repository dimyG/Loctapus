"""Request and response bodies for the upload endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.ingestion.status import RunStatus


class UploadOut(BaseModel):
    """One uploaded file as returned by the API, with its derived latest status."""

    id: UUID
    project_id: UUID
    filename: str
    status: RunStatus
    created_at: datetime
