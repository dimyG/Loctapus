"""Database engine construction and request-scoped session management.

Two session helpers live here: ``session_scope``, the transaction boundary the worker
tasks and the dispatcher loop share, and ``get_db``, the request-scoped FastAPI
dependency. Both bind to the module-level ``engine``.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def make_engine(*, database_url: str) -> Engine:
    """Create a SQLAlchemy engine bound to ``database_url``.

    Every pooled connection is pinged before use (``pool_pre_ping``): a database
    restart under a long-lived worker invalidates pooled connections, and a ping turns
    that into a reconnect instead of a broken task.
    """

    return create_engine(database_url, pool_pre_ping=True)


engine = make_engine(database_url=get_settings().database_url)
# expire_on_commit=False: this app commits reads as transaction boundaries (the
# services' read-only closes), and expiring on those commits would turn the next
# attribute read into a refresh SELECT that re-opens a transaction - pinning a
# pooled connection across the LLM calls that follow. Sessions stay short and
# request-scoped, so cached values cannot go stale enough to matter.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


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
