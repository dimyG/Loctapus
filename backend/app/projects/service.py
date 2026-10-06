from uuid import UUID

from sqlalchemy.orm import Session

from app.identity.models import TeamMembership, User
from app.identity.service import get_personal_context
from app.projects.models import Project, ProjectTeamRole


def create_project(db: Session, user: User, name: str) -> Project:
    workspace, team = get_personal_context(db, user.id)
    project = Project(workspace_id=workspace.id, name=name)
    db.add(project)
    db.flush()
    db.add(ProjectTeamRole(project_id=project.id, team_id=team.id, role="admin"))
    db.commit()
    return project


def _visible_projects_query(db: Session, user: User):
    return (
        db.query(Project)
        .join(ProjectTeamRole, ProjectTeamRole.project_id == Project.id)
        .join(TeamMembership, TeamMembership.team_id == ProjectTeamRole.team_id)
        .filter(TeamMembership.user_id == user.id)
    )


def list_projects(db: Session, user: User) -> list[Project]:
    return _visible_projects_query(db, user).all()


def get_project_for_user(db: Session, user: User, project_id: UUID) -> Project | None:
    return (
        _visible_projects_query(db, user)
        .filter(Project.id == project_id)
        .one_or_none()
    )


def delete_project(db: Session, project: Project) -> None:
    db.query(ProjectTeamRole).filter(
        ProjectTeamRole.project_id == project.id
    ).delete()
    db.delete(project)
    db.commit()
