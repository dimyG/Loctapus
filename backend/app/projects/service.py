"""Business logic for projects and per-team project roles."""

from uuid import UUID

from sqlalchemy.orm import Query, Session

from app.identity.models import Team, TeamMembership, User
from app.projects.models import Project, ProjectTeamRole

# Weakest to strongest; a role grants every permission of the roles below it.
# Keep in sync with the role check constraint in app.projects.models.
ROLE_PRECEDENCE: tuple[str, ...] = ("viewer", "editor", "admin")


def create_project_for_team(*, db: Session, team: Team, name: str) -> Project:
    """Add a project with an admin role for ``team``, without committing.

    The caller owns the surrounding transaction: this helper only flushes, so
    registration and other multi-step flows can still roll the whole thing back.

    :param db: Session the project and its admin role are written through.
    :param team: Team granted the admin role on the new project.
    :param name: Display name of the new project.
    """

    project = Project(workspace_id=team.workspace_id, name=name)
    db.add(project)
    db.flush()
    db.add(ProjectTeamRole(project_id=project.id, team_id=team.id, role="admin"))
    db.flush()
    return project


def _get_team_for_member(*, db: Session, user: User, team_id: UUID) -> Team | None:
    """Return the team when the user is a member of it, otherwise None.

    :param db: Session the membership join runs on.
    :param user: User whose memberships are checked.
    :param team_id: Team the membership must point at.
    """

    return (
        db.query(Team)
        .join(Team.memberships)
        .filter(Team.id == team_id, TeamMembership.user_id == user.id)
        .one_or_none()
    )


def create_project(*, db: Session, user: User, team_id: UUID, name: str) -> Project | None:
    """Create a project on a team the user belongs to, or None when they do not.

    :param db: Session the project is created and committed through.
    :param user: User whose team membership authorizes the creation.
    :param team_id: Team to create the project on.
    :param name: Display name of the new project.
    """

    team = _get_team_for_member(db=db, user=user, team_id=team_id)
    if team is None:
        return None
    project = create_project_for_team(db=db, team=team, name=name)
    db.commit()
    return project


def _visible_projects_query(*, db: Session, user: User) -> Query[Project]:
    """Return the base query for every project shared with one of the user's teams.

    :param db: Session the query is bound to.
    :param user: User whose team memberships scope the visible projects.
    """

    # Distinct keeps a project shared with several of the user's teams to one fetched row.
    return (
        db.query(Project)
        .join(Project.team_roles)
        .join(ProjectTeamRole.team)
        .join(Team.memberships)
        .filter(TeamMembership.user_id == user.id)
        .distinct()
    )


def list_projects(*, db: Session, user: User) -> list[Project]:
    """List projects shared with any of the user's teams.

    :param db: Session the query runs on.
    :param user: User whose team memberships scope the listing.
    """

    return _visible_projects_query(db=db, user=user).all()


def get_project_for_user(*, db: Session, user: User, project_id: UUID) -> Project | None:
    """Return the project by id when shared with the user, otherwise None.

    Unlike ``get_project_visible_to_user``, a public project is not enough:
    the user must hold a role through one of their teams.

    :param db: Session the query runs on.
    :param user: User whose team roles must cover the project.
    :param project_id: Project to look up.
    """

    return _visible_projects_query(db=db, user=user).filter(Project.id == project_id).one_or_none()


def get_project_visible_to_user(*, db: Session, user: User, project_id: UUID) -> Project | None:
    """Return the project by id when shared with the user or public, otherwise None.

    :param db: Session the lookups run on.
    :param user: User the private-project check is scoped to.
    :param project_id: Project to look up.
    """

    project = get_project_for_user(db=db, user=user, project_id=project_id)
    if project is not None:
        return project
    return db.query(Project).filter(Project.id == project_id, Project.is_public.is_(True)).one_or_none()


def list_public_projects(*, db: Session) -> list[Project]:
    """List every public project.

    :param db: Session the query runs on.
    """

    return db.query(Project).filter(Project.is_public.is_(True)).all()


def update_project(
    *,
    db: Session,
    project: Project,
    name: str | None = None,
    is_public: bool | None = None,
) -> Project:
    """Apply the non-None fields and persist.

    A None argument means "leave that field unchanged"; there is no way to
    clear a field through this helper.

    :param db: Session the update commits through.
    :param project: Project instance to mutate.
    :param name: New name, or None to keep the current one.
    :param is_public: New visibility, or None to keep the current one.
    """

    if name is not None:
        project.name = name
    if is_public is not None:
        project.is_public = is_public
    db.commit()
    return project


def _role_at_least(*, role: str, minimum: str) -> bool:
    """Whether ``role`` grants at least the permissions of ``minimum``.

    :param role: Role the caller holds.
    :param minimum: Role whose permissions must be covered.
    """

    return ROLE_PRECEDENCE.index(role) >= ROLE_PRECEDENCE.index(minimum)


def get_effective_role_on_project(*, db: Session, user: User, project_id: UUID) -> str | None:
    """Return the user's strongest role on the project, or None when no team of theirs holds one.

    :param db: Session the role query runs on.
    :param user: User whose teams' roles are compared.
    :param project_id: Project the roles apply to.
    """

    roles = (
        _visible_projects_query(db=db, user=user)
        .filter(Project.id == project_id)
        .with_entities(ProjectTeamRole.role)
        .all()
    )
    strongest: str | None = None
    for row in roles:
        if strongest is None or _role_at_least(role=row.role, minimum=strongest):
            strongest = row.role
    return strongest


def get_project_for_user_with_role(
    *,
    db: Session,
    user: User,
    project_id: UUID,
    minimum_role: str,
) -> Project | None:
    """Return the project when the user's strongest role on it is at least ``minimum_role``.

    :param db: Session the role check and lookup run on.
    :param user: User whose effective role must clear ``minimum_role``.
    :param project_id: Project to return.
    :param minimum_role: Weakest role that still authorizes the caller.
    """

    effective = get_effective_role_on_project(db=db, user=user, project_id=project_id)
    if effective is None or not _role_at_least(role=effective, minimum=minimum_role):
        return None
    return get_project_for_user(db=db, user=user, project_id=project_id)


def delete_project(*, db: Session, project: Project) -> None:
    """Delete a project together with its team roles.

    The role rows go first: the foreign key has no on-delete cascade, so
    deleting the project alone would fail.

    :param db: Session the delete commits through.
    :param project: Project instance to delete.
    """

    db.query(ProjectTeamRole).filter(ProjectTeamRole.project_id == project.id).delete()
    db.delete(project)
    db.commit()
