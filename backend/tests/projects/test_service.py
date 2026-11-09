"""Tests for the project service layer."""

from typing import Any
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.identity import service as identity_service
from app.identity.models import User
from app.projects import service as project_service


def _user(*, db: Session, email: str) -> tuple[User, UUID]:
    """Register an account and return the user with the default team id.

    :param db: Session the registration commits through.
    :param email: Address to register.
    """

    result = identity_service.register_user(db=db, email=email, password="password123")
    return result.user, result.team.id


def test_create_project_grants_personal_team_admin(*, db_session: Session) -> None:
    """Check that creating a project gives the creator's team an admin role.

    :param db_session: Transaction-managed session the creation runs on.
    """

    user, team_id = _user(db=db_session, email="owner@example.com")
    project = project_service.create_project(db=db_session, user=user, team_id=team_id, name="kb1")
    assert project is not None
    fetched = project_service.get_project_for_user(db=db_session, user=user, project_id=project.id)
    assert fetched and fetched.name == "kb1"


def test_list_projects_scopes_to_user(*, db_session: Session) -> None:
    """Check that projects are only visible through the user's own teams.

    :param db_session: Transaction-managed session the two accounts are created on.
    """

    alice, alice_team_id = _user(db=db_session, email="alice@example.com")
    bob, bob_team_id = _user(db=db_session, email="bob@example.com")
    project_service.create_project(db=db_session, user=alice, team_id=alice_team_id, name="alice-kb")
    project_service.create_project(db=db_session, user=bob, team_id=bob_team_id, name="bob-kb")
    assert sorted(p.name for p in project_service.list_projects(db=db_session, user=alice)) == [
        "Default",
        "alice-kb",
    ]
    assert (
        project_service.get_project_for_user(
            db=db_session,
            user=alice,
            project_id=project_service.list_projects(db=db_session, user=bob)[0].id,
        )
        is None
    )


def test_delete_project_removes_visibility(*, db_session: Session) -> None:
    """Check that deleting a project removes it from listings.

    :param db_session: Transaction-managed session the project is created and deleted on.
    """

    user, team_id = _user(db=db_session, email="del@example.com")
    project = project_service.create_project(db=db_session, user=user, team_id=team_id, name="gone")
    assert project is not None
    project_service.delete_project(db=db_session, project=project)
    assert project_service.get_project_for_user(db=db_session, user=user, project_id=project.id) is None


def test_get_project_for_user_with_role_requires_admin(*, db_session: Session) -> None:
    """Check that the admin-role lookup ignores viewer roles.

    :param db_session: Transaction-managed session the roles are written through.
    """

    from app.projects.models import ProjectTeamRole

    owner, owner_team_id = _user(db=db_session, email="owner2@example.com")
    project = project_service.create_project(db=db_session, user=owner, team_id=owner_team_id, name="shared")
    assert project is not None

    # A second user whose team holds only a viewer role on the project.
    viewer, viewer_team_id = _user(db=db_session, email="viewer@example.com")
    db_session.add(ProjectTeamRole(project_id=project.id, team_id=viewer_team_id, role="viewer"))
    db_session.flush()

    admin_view = project_service.get_project_for_user_with_role(
        db=db_session, user=owner, project_id=project.id, minimum_role="admin"
    )
    viewer_view = project_service.get_project_for_user_with_role(
        db=db_session, user=viewer, project_id=project.id, minimum_role="admin"
    )
    assert admin_view is not None
    assert viewer_view is None


def test_effective_role_is_strongest_across_teams(*, db_session: Session) -> None:
    """Check that the effective role is the strongest among the user's teams' roles.

    :param db_session: Transaction-managed session the second team is created on.
    """

    from app.identity.models import Team, TeamMembership
    from app.projects.models import ProjectTeamRole

    registered = identity_service.register_user(
        db=db_session, email="strongest@example.com", password="password123"
    )
    owner = registered.user
    project = project_service.create_project(
        db=db_session, user=owner, team_id=registered.team.id, name="strong"
    )
    assert project is not None

    # A second team of the same user holds only a viewer role on the project.
    second_team = Team(workspace_id=registered.workspace.id, name="Second")
    db_session.add(second_team)
    db_session.flush()
    db_session.add(TeamMembership(team_id=second_team.id, user_id=owner.id))
    db_session.add(ProjectTeamRole(project_id=project.id, team_id=second_team.id, role="viewer"))
    db_session.flush()

    assert (
        project_service.get_effective_role_on_project(db=db_session, user=owner, project_id=project.id)
        == "admin"
    )
    # The strongest role subsumes weaker ones, so the admin passes a viewer-level check.
    assert (
        project_service.get_project_for_user_with_role(
            db=db_session, user=owner, project_id=project.id, minimum_role="viewer"
        )
        is not None
    )
    assert (
        project_service.get_project_for_user_with_role(
            db=db_session, user=owner, project_id=project.id, minimum_role="admin"
        )
        is not None
    )


def test_effective_role_is_none_without_access(*, db_session: Session) -> None:
    """Check that the effective role is None when no team of the user holds one.

    :param db_session: Transaction-managed session the two accounts are created on.
    """

    owner, owner_team_id = _user(db=db_session, email="er-owner@example.com")
    stranger, _stranger_team_id = _user(db=db_session, email="er-stranger@example.com")
    project = project_service.create_project(db=db_session, user=owner, team_id=owner_team_id, name="er")
    assert project is not None
    assert (
        project_service.get_effective_role_on_project(db=db_session, user=stranger, project_id=project.id)
        is None
    )


def test_duplicate_project_name_allowed(*, db_session: Session) -> None:
    """Check that two projects may share a name.

    :param db_session: Transaction-managed session the two creations run on.
    """

    user, team_id = _user(db=db_session, email="dupe@example.com")
    a = project_service.create_project(db=db_session, user=user, team_id=team_id, name="same")
    b = project_service.create_project(db=db_session, user=user, team_id=team_id, name="same")
    assert a is not None and b is not None
    assert a.id != b.id
    assert len(project_service.list_projects(db=db_session, user=user)) == 3


def test_visibility_deduplicates_projects_shared_with_multiple_teams(*, db_session: Session) -> None:
    """Check that a project shared with two of the user's teams appears once.

    :param db_session: Transaction-managed session the second team is created on.
    """

    from app.identity.models import Team, TeamMembership
    from app.projects.models import ProjectTeamRole

    registered = identity_service.register_user(
        db=db_session, email="dedup@example.com", password="password123"
    )
    owner = registered.user
    project = project_service.create_project(
        db=db_session, user=owner, team_id=registered.team.id, name="shared"
    )
    assert project is not None

    # A second team of the same user also holds a role on the project.
    second_team = Team(workspace_id=registered.workspace.id, name="Second")
    db_session.add(second_team)
    db_session.flush()
    db_session.add(TeamMembership(team_id=second_team.id, user_id=owner.id))
    db_session.add(ProjectTeamRole(project_id=project.id, team_id=second_team.id, role="viewer"))
    db_session.flush()

    visible = project_service.list_projects(db=db_session, user=owner)
    assert sorted(p.name for p in visible) == ["Default", "shared"]
    assert project_service.get_project_for_user(db=db_session, user=owner, project_id=project.id) is not None


def test_list_projects_fetches_each_project_once(*, db_session: Session) -> None:
    """Check that list_projects issues a DISTINCT select, not one row per sharing team.

    :param db_session: Transaction-managed session whose statements are captured.
    """

    bind = db_session.bind
    assert bind is not None
    statements: list[str] = []

    # SQLAlchemy calls before_cursor_execute with fixed positional arguments.
    def _capture(  # noqa: PLR0917
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        """Record every statement the session executes.

        :param conn: Connection executing the statement; unused here.
        :param cursor: Cursor the statement runs on; unused here.
        :param statement: SQL text about to execute.
        :param parameters: Bound parameters of the statement; unused here.
        :param context: Execution context of the statement; unused here.
        :param executemany: Whether this is a many-row execute; unused here.
        """

        statements.append(statement)

    user, _team_id = _user(db=db_session, email="distinct@example.com")
    event.listen(bind, "before_cursor_execute", _capture)
    try:
        project_service.list_projects(db=db_session, user=user)
    finally:
        event.remove(bind, "before_cursor_execute", _capture)

    project_selects = [s for s in statements if "FROM projects" in s]
    assert project_selects, "expected a projects select to run"
    assert any("SELECT DISTINCT" in s.upper() for s in project_selects)


def test_get_project_visible_to_user_allows_public(*, db_session: Session) -> None:
    """Check that making a project public exposes it to strangers.

    :param db_session: Transaction-managed session the visibility flip runs on.
    """

    owner, owner_team_id = _user(db=db_session, email="vis-owner@example.com")
    stranger, _ = _user(db=db_session, email="vis-stranger@example.com")
    project = project_service.create_project(db=db_session, user=owner, team_id=owner_team_id, name="vis")
    assert project is not None
    assert (
        project_service.get_project_visible_to_user(db=db_session, user=stranger, project_id=project.id)
        is None
    )
    project.is_public = True
    db_session.commit()
    assert (
        project_service.get_project_visible_to_user(db=db_session, user=stranger, project_id=project.id)
        is not None
    )


def test_list_public_projects_only_returns_public(*, db_session: Session) -> None:
    """Check that the public listing hides private projects.

    :param db_session: Transaction-managed session the two projects are created on.
    """

    owner, owner_team_id = _user(db=db_session, email="lp-owner@example.com")
    project_service.create_project(db=db_session, user=owner, team_id=owner_team_id, name="lp-private")
    public_p = project_service.create_project(
        db=db_session, user=owner, team_id=owner_team_id, name="lp-public"
    )
    assert public_p is not None
    public_p.is_public = True
    db_session.commit()
    assert [x.id for x in project_service.list_public_projects(db=db_session)] == [public_p.id]


def test_update_project_name_and_visibility(*, db_session: Session) -> None:
    """Check that update applies name and visibility.

    :param db_session: Transaction-managed session the update commits through.
    """

    owner, owner_team_id = _user(db=db_session, email="up-owner@example.com")
    p = project_service.create_project(db=db_session, user=owner, team_id=owner_team_id, name="before")
    assert p is not None
    updated = project_service.update_project(db=db_session, project=p, name="after", is_public=True)
    assert updated.name == "after" and updated.is_public is True
