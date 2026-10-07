import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    owned_workspaces: Mapped[list["Workspace"]] = relationship(back_populates="owner")
    memberships: Mapped[list["TeamMembership"]] = relationship(back_populates="user")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))

    owner: Mapped["User"] = relationship(back_populates="owned_workspaces")
    teams: Mapped[list["Team"]] = relationship(back_populates="workspace")
    projects: Mapped[list["Project"]] = relationship(back_populates="workspace")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String)

    workspace: Mapped["Workspace"] = relationship(back_populates="teams")
    memberships: Mapped[list["TeamMembership"]] = relationship(back_populates="team")
    project_roles: Mapped[list["ProjectTeamRole"]] = relationship(back_populates="team")


class TeamMembership(Base):
    __tablename__ = "team_memberships"
    __table_args__ = (UniqueConstraint("team_id", "user_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))

    team: Mapped["Team"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String, primary_key=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime] = mapped_column(server_default=func.now())
