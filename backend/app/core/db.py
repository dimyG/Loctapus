"""Database engine construction and request-scoped session management."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def make_engine(*, database_url: str) -> Engine:
    """Create a SQLAlchemy engine bound to ``database_url``."""

    return create_engine(database_url)


SessionLocal = sessionmaker(bind=make_engine(database_url=get_settings().database_url))


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a session that commits on success, rolls back on error, and always closes.

    Workers run outside HTTP, so the request-scoped ``get_db`` does not apply; this is
    the transaction boundary their tasks and the dispatcher loop share.
    """

    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """Yield a request-scoped session and close it once the request finishes."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
