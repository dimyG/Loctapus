import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ProjectTeamRole(Base):
    __tablename__ = "project_team_roles"
    __table_args__ = (
        UniqueConstraint("project_id", "team_id"),
        CheckConstraint("role IN ('admin', 'editor', 'viewer')"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"))
    role: Mapped[str] = mapped_column(String)
