"""Request and response bodies for the project endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    """Body for project creation."""

    name: str = Field(min_length=1, max_length=200)
    team_id: UUID


class ProjectUpdate(BaseModel):
    """Body for partial project updates; omitted fields are left unchanged."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_public: bool | None = None


class ProjectOut(BaseModel):
    """Project as returned by the API."""

    id: UUID
    name: str
    is_public: bool
    created_at: datetime
