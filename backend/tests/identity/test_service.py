import pytest

from app.identity import service
from app.identity.models import User


def test_register_creates_default_graph(db_session):
    result = service.register_user(db_session, "new@example.com", "password123")
    assert result.workspace.owner_user_id == result.user.id
    assert result.team.workspace_id == result.workspace.id
    assert result.workspace.name == "Default" and result.team.name == "Default"
    assert result.project.name == "Default" and result.project.is_public is False
    assert result.project.workspace_id == result.workspace.id


def test_register_rolls_back_if_project_creation_fails(db_session, monkeypatch):
    from app.projects import service as projects_service

    def boom(*args, **kwargs):
        raise RuntimeError("project creation failed")

    monkeypatch.setattr(projects_service, "create_project_for_team", boom)
    with pytest.raises(RuntimeError):
        service.register_user(db_session, "fail@example.com", "password123")
    assert db_session.query(User).filter_by(email="fail@example.com").one_or_none() is None


def test_register_duplicate_email_raises(db_session):
    service.register_user(db_session, "dup@example.com", "password123")
    with pytest.raises(service.EmailAlreadyRegistered):
        service.register_user(db_session, "DUP@example.com", "password123")


def test_authenticate_user(db_session):
    service.register_user(db_session, "auth@example.com", "password123")
    assert service.authenticate_user(db_session, "auth@example.com", "password123")
    assert service.authenticate_user(db_session, "auth@example.com", "wrong") is None
    assert service.authenticate_user(db_session, "ghost@example.com", "password123") is None
