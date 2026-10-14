"""ORM models for users, workspaces, teams, and token revocation."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base

if TYPE_CHECKING:
    from app.projects.models import Project, ProjectTeamRole


class User(Base):
    """A registered account with email credentials."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owned_workspaces: Mapped[list[Workspace]] = relationship(back_populates="owner")
    memberships: Mapped[list[TeamMembership]] = relationship(back_populates="user")


class Workspace(Base):
    """A tenant that groups teams and projects, owned by a user."""

    __tablename__ = "workspaces"
    # Postgres does not index foreign key columns on its own; joins and ownership
    # lookups filter on this one.
    __table_args__ = (Index("ix_workspaces_owner_user_id", "owner_user_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String)
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))

    owner: Mapped[User] = relationship(back_populates="owned_workspaces")
    teams: Mapped[list[Team]] = relationship(back_populates="workspace")
    projects: Mapped[list[Project]] = relationship(back_populates="workspace")


class Team(Base):
    """A group of users inside a workspace, granted project roles as a unit."""

    __tablename__ = "teams"
    __table_args__ = (Index("ix_teams_workspace_id", "workspace_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String)

    workspace: Mapped[Workspace] = relationship(back_populates="teams")
    memberships: Mapped[list[TeamMembership]] = relationship(back_populates="team")
    project_roles: Mapped[list[ProjectTeamRole]] = relationship(back_populates="team")


class TeamMembership(Base):
    """Membership of one user in one team."""

    __tablename__ = "team_memberships"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id"),
        # The composite unique above covers only the leading team_id column.
        Index("ix_team_memberships_user_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))

    team: Mapped[Team] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class RevokedToken(Base):
    """A revoked JWT ID, kept until the token would have expired anyway."""

    __tablename__ = "revoked_tokens"

    # Jti is the JWT ID claim, the handle used to revoke tokens before their natural expiry.
    jti: Mapped[str] = mapped_column(String, primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
