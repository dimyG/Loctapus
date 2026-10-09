"""Request and response bodies for the project endpoints."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ProjectCreate(BaseModel):
    """Body for project creation."""

    name: str = Field(min_length=1, max_length=200)
    team_id: UUID


class ProjectUpdate(BaseModel):
    """Body for partial project updates; omitted fields stay unchanged, explicit nulls are rejected."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_public: bool | None = None

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> Self:
        """Fail when a field is explicitly set to null instead of omitted."""

        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} must not be null; omit the field to leave it unchanged")
        return self


class ProjectOut(BaseModel):
    """Project as returned by the API."""

    id: UUID
    name: str
    is_public: bool
    created_at: datetime
