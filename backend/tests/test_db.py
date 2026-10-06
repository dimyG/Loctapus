from sqlalchemy import text

from app.core.db import make_engine


def test_make_engine_connects(engine):
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_db_session_fixture_works(db_session):
    assert db_session.execute(text("SELECT 1")).scalar() == 1
