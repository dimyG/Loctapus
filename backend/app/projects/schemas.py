from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    team_id: UUID


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_public: bool | None = None


class ProjectOut(BaseModel):
    id: UUID
    name: str
    is_public: bool
    created_at: datetime
