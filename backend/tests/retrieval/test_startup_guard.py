"""Tests for the API startup dimension guard."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.main import app


class _MismatchedProvider:
    """A provider whose dimension disagrees with the stub-migrated catalog."""

    dimension: int = 9999


def test_lifespan_runs_startup_checks(*, engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that the lifespan runs the dimension guard once at startup.

    :param engine: Session-scoped engine bound to the migration-built test database.
    :param monkeypatch: Redirects ``app.main.SessionLocal`` and installs the recording guard.
    """

    calls: list[object] = []

    def _record_call(*, db: object, embedding_provider: object) -> None:
        """Record one startup-guard call so this test can assert it ran.

        :param db: Session the guard would have run on.
        :param embedding_provider: Provider whose dimension the guard would check.
        """

        calls.append(db)

    monkeypatch.setattr("app.main.SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    monkeypatch.setattr("app.main.run_startup_checks", _record_call)
    with TestClient(app):
        pass
    assert calls


def test_guard_refuses_mismatched_dimension(*, engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that a provider dimension that disagrees with the catalog refuses startup.

    :param engine: Session-scoped engine bound to the migration-built test database.
    :param monkeypatch: Redirects ``app.main.SessionLocal`` and injects the mismatched provider.
    """

    monkeypatch.setattr("app.main.SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    monkeypatch.setattr("app.main.get_embedding_provider", _mismatched_provider)
    with pytest.raises(RuntimeError, match="chunks.embedding is vector"), TestClient(app):
        pass


def _mismatched_provider(*, settings: object) -> _MismatchedProvider:
    """Return the mismatched provider the refusal test injects.

    :param settings: Settings the factory would dispatch on; unused by this fake.
    """

    return _MismatchedProvider()
