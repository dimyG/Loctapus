"""Request and response bodies for the identity endpoints."""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Body for account registration."""

    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    """Body for credential verification."""

    email: EmailStr
    password: str


class WorkspaceOut(BaseModel):
    """Workspace as returned by the API."""

    id: UUID
    name: str


class TeamOut(BaseModel):
    """Team as returned by the API."""

    id: UUID
    name: str
    workspace_id: UUID
