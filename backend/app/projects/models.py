"""ORM models for projects and per-team project roles."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base

if TYPE_CHECKING:
    from app.identity.models import Team, Workspace


class Project(Base):
    """A unit of work created by a team inside a workspace, with per-team visibility."""

    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_workspace_id", "workspace_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String)
    is_public: Mapped[bool] = mapped_column(default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped[Workspace] = relationship(back_populates="projects")
    team_roles: Mapped[list[ProjectTeamRole]] = relationship(back_populates="project")


class ProjectTeamRole(Base):
    """A team's role on a project, one of admin, editor, or viewer."""

    __tablename__ = "project_team_roles"
    __table_args__ = (
        UniqueConstraint("project_id", "team_id"),
        CheckConstraint("role IN ('admin', 'editor', 'viewer')"),
        # The composite unique above covers only the leading project_id column.
        Index("ix_project_team_roles_team_id", "team_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    role: Mapped[str] = mapped_column(String)

    project: Mapped[Project] = relationship(back_populates="team_roles")
    team: Mapped[Team] = relationship(back_populates="project_roles")
