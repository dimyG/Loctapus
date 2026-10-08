"""Database engine construction and request-scoped session management."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def make_engine(*, database_url: str) -> Engine:
    """Create a SQLAlchemy engine bound to ``database_url``."""

    return create_engine(database_url)


SessionLocal = sessionmaker(bind=make_engine(database_url=get_settings().database_url))


def get_db() -> Iterator[Session]:
    """Yield a request-scoped session and close it once the request finishes."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
