from uuid import UUID

from sqlalchemy.orm import Session

from app.identity.models import Team, TeamMembership, User
from app.projects.models import Project, ProjectTeamRole


def create_project_for_team(db: Session, team: Team, name: str) -> Project:
    project = Project(workspace_id=team.workspace_id, name=name)
    db.add(project)
    db.flush()
    db.add(ProjectTeamRole(project_id=project.id, team_id=team.id, role="admin"))
    db.flush()
    return project


def _get_team_for_member(db: Session, user: User, team_id: UUID) -> Team | None:
    return (
        db.query(Team)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .filter(Team.id == team_id, TeamMembership.user_id == user.id)
        .one_or_none()
    )


def create_project(db: Session, user: User, team_id: UUID, name: str) -> Project | None:
    team = _get_team_for_member(db, user, team_id)
    if team is None:
        return None
    project = create_project_for_team(db, team, name)
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


def get_project_for_user_with_role(
    db: Session, user: User, project_id: UUID, roles: tuple[str, ...]
) -> Project | None:
    return (
        _visible_projects_query(db, user)
        .filter(Project.id == project_id, ProjectTeamRole.role.in_(roles))
        .one_or_none()
    )


def delete_project(db: Session, project: Project) -> None:
    db.query(ProjectTeamRole).filter(
        ProjectTeamRole.project_id == project.id
    ).delete()
    db.delete(project)
    db.commit()
