"""Tests for the identity service layer."""

import pytest
from sqlalchemy.orm import Session

from app.identity import service
from app.identity.models import User


def test_register_creates_default_graph(db_session: Session) -> None:
    """Check that registration provisions the default workspace, team, and project."""

    result = service.register_user(db_session, "new@example.com", "password123")
    assert result.workspace.owner_user_id == result.user.id
    assert result.team.workspace_id == result.workspace.id
    assert result.workspace.name == "Default" and result.team.name == "Default"
    assert result.project.name == "Default" and result.project.is_public is False
    assert result.project.workspace_id == result.workspace.id


def test_register_rolls_back_if_project_creation_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that a failed registration leaves no partial rows behind."""

    def boom(*args: object, **kwargs: object) -> None:
        """Fail project creation to exercise the rollback path."""

        raise RuntimeError("project creation failed")

    monkeypatch.setattr(service, "create_project_for_team", boom)
    with pytest.raises(RuntimeError):
        service.register_user(db_session, "fail@example.com", "password123")
    assert db_session.query(User).filter_by(email="fail@example.com").one_or_none() is None


def test_register_duplicate_email_raises(db_session: Session) -> None:
    """Check that re-registering an email (case-insensitive) raises."""

    service.register_user(db_session, "dup@example.com", "password123")
    with pytest.raises(service.EmailAlreadyRegisteredError):
        service.register_user(db_session, "DUP@example.com", "password123")


def test_authenticate_user(db_session: Session) -> None:
    """Check password verification and unknown-user handling."""

    service.register_user(db_session, "auth@example.com", "password123")
    assert service.authenticate_user(db_session, "auth@example.com", "password123")
    assert service.authenticate_user(db_session, "auth@example.com", "wrong") is None
    assert service.authenticate_user(db_session, "ghost@example.com", "password123") is None
