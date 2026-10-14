"""Tests for engine construction and the session fixture."""

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import make_engine


def test_engine_pings_connections_before_use() -> None:
    """Check that every pooled connection is pinged before the pool hands it out."""

    engine = make_engine(database_url="postgresql+psycopg://rag:rag@localhost:5432/rag")
    # _pre_ping is the pool's private flag; a pre-ping engine builds True here.
    assert engine.pool._pre_ping is True
    engine.dispose()


def test_make_engine_connects(*, settings: Settings, engine: Engine) -> None:
    """Check that an engine built directly from settings can connect and select.

    The session-scoped ``engine`` fixture is requested so the migrated test database
    exists before the direct connection is attempted.
    """

    settings_engine = make_engine(database_url=settings.database_url)
    with settings_engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
    settings_engine.dispose()


def test_db_session_fixture_works(*, db_session: Session) -> None:
    """Check that the rollback-managed session can select."""

    assert db_session.execute(text("SELECT 1")).scalar() == 1
