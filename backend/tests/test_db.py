"""Tests for engine construction and the session fixture."""

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def test_make_engine_connects(engine: Engine) -> None:
    """Check that a connection through the migrated engine can select."""

    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_db_session_fixture_works(db_session: Session) -> None:
    """Check that the rollback-managed session can select."""

    assert db_session.execute(text("SELECT 1")).scalar() == 1
