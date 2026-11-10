"""Tests for the identity service layer."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.identity import service
from app.identity.models import RevokedToken, User


def test_register_creates_default_graph(*, db_session: Session) -> None:
    """Check that registration provisions the default workspace, team, and project.

    :param db_session: Transaction-managed session the registration runs on.
    """

    result = service.register_user(db=db_session, email="new@example.com", password="password123")
    assert result.workspace.owner_user_id == result.user.id
    assert result.team.workspace_id == result.workspace.id
    assert result.workspace.name == "Default" and result.team.name == "Default"
    assert result.project.name == "Default" and result.project.is_public is False
    assert result.project.workspace_id == result.workspace.id


def test_register_rolls_back_if_project_creation_fails(
    *, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that a failed registration leaves no partial rows behind.

    :param db_session: Transaction-managed session the registration runs on.
    :param monkeypatch: Fixture installing the failing project-creation stub.
    """

    def boom(*args: object, **kwargs: object) -> None:
        """Fail project creation to exercise the rollback path.

        :param args: Unused catch-all; the real call is keyword-only, so it stays empty.
        :param kwargs: Keyword arguments the patched call passes; unused here.
        """

        raise RuntimeError("project creation failed")

    monkeypatch.setattr(service, "create_project_for_team", boom)
    with pytest.raises(RuntimeError):
        service.register_user(db=db_session, email="fail@example.com", password="password123")
    assert db_session.query(User).filter_by(email="fail@example.com").one_or_none() is None


def test_register_duplicate_email_raises(*, db_session: Session) -> None:
    """Check that re-registering an email (case-insensitive) raises.

    :param db_session: Transaction-managed session the registrations run on.
    """

    service.register_user(db=db_session, email="dup@example.com", password="password123")
    with pytest.raises(service.EmailAlreadyRegisteredError):
        service.register_user(db=db_session, email="DUP@example.com", password="password123")


def test_register_provisioning_failure_not_email_conflict(
    *, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that a constraint failure while provisioning surfaces as itself, not a 409.

    :param db_session: Transaction-managed session the registration runs on.
    :param monkeypatch: Fixture installing the failing provisioning stub.
    """

    def boom(*args: object, **kwargs: object) -> None:
        """Fail provisioning to exercise the propagation path.

        :param args: Unused catch-all; the real call is keyword-only, so it stays empty.
        :param kwargs: Keyword arguments the patched call passes; unused here.
        """

        raise IntegrityError("insert into workspaces", {}, Exception("check violation"))

    monkeypatch.setattr(service, "create_project_for_team", boom)
    with pytest.raises(IntegrityError):
        service.register_user(db=db_session, email="prov@example.com", password="password123")
    assert db_session.query(User).filter_by(email="prov@example.com").one_or_none() is None


def test_authenticate_user(*, db_session: Session) -> None:
    """Check that only a correct password for a known email authenticates.

    :param db_session: Transaction-managed session the registration and lookups run on.
    """

    service.register_user(db=db_session, email="auth@example.com", password="password123")
    assert service.authenticate_user(db=db_session, email="auth@example.com", password="password123")
    assert service.authenticate_user(db=db_session, email="auth@example.com", password="wrong") is None
    assert service.authenticate_user(db=db_session, email="ghost@example.com", password="password123") is None


def test_revoke_token_tolerates_concurrent_duplicate(
    *, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that a second, concurrent revoke of the same jti cannot raise IntegrityError.

    :param db_session: Transaction-managed session the revocations run on.
    :param monkeypatch: Fixture installing the always-unrevoked pre-check stub.
    """

    expires_at = datetime.now(UTC)
    service.revoke_token(db=db_session, jti="race-jti", expires_at=expires_at)

    # Simulate the losing interleaving of two concurrent logouts: both pre-checks miss
    # the row, so both inserts run. With check-then-insert the second one raises.
    def blind(*, db: Session, jti: str) -> bool:
        """Report every token as unrevoked, as a concurrent pre-check would.

        :param db: Session the real pre-check would query; unused here.
        :param jti: Token id the real pre-check would look up; unused here.
        """

        return False

    monkeypatch.setattr(service, "is_token_revoked", blind)
    service.revoke_token(db=db_session, jti="race-jti", expires_at=expires_at)
    assert db_session.get(RevokedToken, "race-jti") is not None
