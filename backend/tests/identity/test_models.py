"""Tests for the identity ORM models against a real database."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.identity.models import Team, TeamMembership, User, Workspace
from app.projects.models import Project, ProjectTeamRole


def _make_user(db: Session, email: str = "a@example.com") -> tuple[User, Workspace, Team]:
    """Create a user with a default workspace, team, and membership."""

    user = User(email=email, password_hash="x")
    db.add(user)
    db.flush()
    ws = Workspace(name="Default", owner_user_id=user.id)
    db.add(ws)
    db.flush()
    team = Team(workspace_id=ws.id, name="Default")
    db.add(team)
    db.flush()
    db.add(TeamMembership(team_id=team.id, user_id=user.id))
    db.flush()
    return user, ws, team


def test_register_graph_persists(db_session: Session) -> None:
    """Check that the user, workspace, team, and membership rows persist."""

    user, ws, team = _make_user(db_session)
    assert user.id and ws.owner_user_id == user.id and team.workspace_id == ws.id


def test_team_membership_unique(db_session: Session) -> None:
    """Check that a duplicate team membership violates the unique constraint."""

    user, ws, team = _make_user(db_session)
    db_session.add(TeamMembership(team_id=team.id, user_id=user.id))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_project_team_role_unique_and_role_check(db_session: Session) -> None:
    """Check the role check constraint and the per-team uniqueness of project roles."""

    user, ws, team = _make_user(db_session)
    project = Project(workspace_id=ws.id, name="p1")
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectTeamRole(project_id=project.id, team_id=team.id, role="admin"))
    db_session.flush()
    db_session.add(ProjectTeamRole(project_id=project.id, team_id=team.id, role="viewer"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    user, ws, team = _make_user(db_session, email="b@example.com")
    project = Project(workspace_id=ws.id, name="p2")
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectTeamRole(project_id=project.id, team_id=team.id, role="owner"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_revoked_token_roundtrip(db_session: Session) -> None:
    """Check that a revoked token row round-trips by jti."""

    from app.identity.models import RevokedToken

    db_session.add(RevokedToken(jti="abc123", expires_at=datetime.now(UTC)))
    db_session.flush()
    assert db_session.query(RevokedToken).filter_by(jti="abc123").one().jti == "abc123"


def test_relationships_traverse(db_session: Session) -> None:
    """Check that every declared relationship traverses both ways."""

    user, ws, team = _make_user(db_session, email="rel@example.com")
    project = Project(workspace_id=ws.id, name="rel-p")
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectTeamRole(project_id=project.id, team_id=team.id, role="admin"))
    db_session.flush()
    assert user.owned_workspaces[0].id == ws.id
    assert ws.teams[0].id == team.id
    assert team.workspace.id == ws.id
    assert user.memberships[0].team_id == team.id
    assert project.workspace.id == ws.id
    assert project.team_roles[0].team_id == team.id
    assert team.project_roles[0].project_id == project.id
