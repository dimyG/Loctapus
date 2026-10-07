import pytest

from app.identity import service


def test_register_creates_full_personal_graph(db_session):
    result = service.register_user(db_session, "new@example.com", "password123")
    assert result.workspace.owner_user_id == result.user.id
    assert result.team.workspace_id == result.workspace.id
    ws, team = service.get_personal_context(db_session, result.user.id)
    assert ws.id == result.workspace.id and team.id == result.team.id


def test_register_duplicate_email_raises(db_session):
    service.register_user(db_session, "dup@example.com", "password123")
    with pytest.raises(service.EmailAlreadyRegistered):
        service.register_user(db_session, "DUP@example.com", "password123")


def test_authenticate_user(db_session):
    service.register_user(db_session, "auth@example.com", "password123")
    assert service.authenticate_user(db_session, "auth@example.com", "password123")
    assert service.authenticate_user(db_session, "auth@example.com", "wrong") is None
    assert service.authenticate_user(db_session, "ghost@example.com", "password123") is None
