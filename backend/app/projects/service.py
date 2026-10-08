"""Business logic for projects and per-team project roles."""

from uuid import UUID

from sqlalchemy.orm import Query, Session

from app.identity.models import Team, TeamMembership, User
from app.projects.models import Project, ProjectTeamRole


def create_project_for_team(*, db: Session, team: Team, name: str) -> Project:
    """Add a project with an admin role for ``team``, without committing."""

    project = Project(workspace_id=team.workspace_id, name=name)
    db.add(project)
    db.flush()
    db.add(ProjectTeamRole(project_id=project.id, team_id=team.id, role="admin"))
    db.flush()
    return project


def _get_team_for_member(*, db: Session, user: User, team_id: UUID) -> Team | None:
    """Return the team when the user is a member of it, otherwise None."""

    return (
        db.query(Team)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .filter(Team.id == team_id, TeamMembership.user_id == user.id)
        .one_or_none()
    )


def create_project(*, db: Session, user: User, team_id: UUID, name: str) -> Project | None:
    """Create a project on a team the user belongs to, or None when they do not."""

    team = _get_team_for_member(db=db, user=user, team_id=team_id)
    if team is None:
        return None
    project = create_project_for_team(db=db, team=team, name=name)
    db.commit()
    return project


def _visible_projects_query(*, db: Session, user: User) -> Query[Project]:
    """Return the base query for every project shared with one of the user's teams."""

    return (
        db.query(Project)
        .join(ProjectTeamRole, ProjectTeamRole.project_id == Project.id)
        .join(TeamMembership, TeamMembership.team_id == ProjectTeamRole.team_id)
        .filter(TeamMembership.user_id == user.id)
    )


def list_projects(*, db: Session, user: User) -> list[Project]:
    """List projects shared with any of the user's teams."""

    return _visible_projects_query(db=db, user=user).all()


def get_project_for_user(*, db: Session, user: User, project_id: UUID) -> Project | None:
    """Return the project by id when shared with the user, otherwise None."""

    return _visible_projects_query(db=db, user=user).filter(Project.id == project_id).one_or_none()


def get_project_visible_to_user(*, db: Session, user: User, project_id: UUID) -> Project | None:
    """Return the project by id when shared with the user or public, otherwise None."""

    project = get_project_for_user(db=db, user=user, project_id=project_id)
    if project is not None:
        return project
    return db.query(Project).filter(Project.id == project_id, Project.is_public.is_(True)).one_or_none()


def list_public_projects(*, db: Session) -> list[Project]:
    """List every public project."""

    return db.query(Project).filter(Project.is_public.is_(True)).all()


def update_project(
    *,
    db: Session,
    project: Project,
    name: str | None = None,
    is_public: bool | None = None,
) -> Project:
    """Apply the non-None fields and persist."""

    if name is not None:
        project.name = name
    if is_public is not None:
        project.is_public = is_public
    db.commit()
    return project


def get_project_for_user_with_role(
    *,
    db: Session,
    user: User,
    project_id: UUID,
    roles: tuple[str, ...],
) -> Project | None:
    """Return the project when one of the user's teams holds one of ``roles`` on it."""

    return (
        _visible_projects_query(db=db, user=user)
        .filter(Project.id == project_id, ProjectTeamRole.role.in_(roles))
        .one_or_none()
    )


def delete_project(*, db: Session, project: Project) -> None:
    """Delete a project together with its team roles."""

    db.query(ProjectTeamRole).filter(ProjectTeamRole.project_id == project.id).delete()
    db.delete(project)
    db.commit()
