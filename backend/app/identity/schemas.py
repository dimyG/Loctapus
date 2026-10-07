from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class WorkspaceOut(BaseModel):
    id: UUID
    name: str


class TeamOut(BaseModel):
    id: UUID
    name: str
    workspace_id: UUID
