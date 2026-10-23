"""Shared fixtures that provision an isolated, migration-built test database and broker vhost."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import Settings
from app.core.db import get_db, make_engine
from app.main import app
from app.storage.service import StorageService
from scripts.broker_admin import ensure_broker_vhost
from tests.helpers import SettingsForTests

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEST_URL = "postgresql+psycopg://rag:rag@localhost:5432/rag_test"
DEFAULT_TEST_BROKER_URL = "amqp://guest:guest@localhost:5672/rag_test"


@pytest.fixture
def settings() -> Settings:
    """Return settings pointing at the disposable test database."""

    return SettingsForTests(
        database_url=os.environ.get("RAG_TEST_DATABASE_URL", DEFAULT_TEST_URL),
        jwt_secret="test-secret",
    )


@pytest.fixture
def storage(*, settings: Settings) -> StorageService:
    """Return the real storage service pointed at the compose Garage with the dev bucket."""

    return StorageService(settings=settings)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Create the test database through migrations, and drop it after the session."""

    url = os.environ.get("RAG_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    db_name = url.rsplit("/", 1)[1]

    admin = make_engine(database_url=admin_url).execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": db_name}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin.dispose()

    test_engine = make_engine(database_url=url)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")

    yield test_engine

    test_engine.dispose()
    with admin.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": db_name},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def broker_url() -> str:
    """Ensure the ``rag_test`` vhost exists with its user's permissions, then return its URL."""

    url = os.environ.get("RAG_TEST_BROKER_URL", DEFAULT_TEST_BROKER_URL)
    ensure_broker_vhost(broker_url=url)
    return url


@pytest.fixture
def db_session(*, engine: Engine) -> Iterator[Session]:
    """Return a session bound to a transaction that is rolled back after the test."""

    connection = engine.connect()
    transaction = connection.begin()
    # The savepoint mode keeps service-level commit() inside the fixture's transaction:
    # commit releases and recreates the savepoint, and teardown stays warning-free.
    # expire_on_commit matches the app's SessionLocal, so services under test read
    # their just-committed rows the same way production does.
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(*, db_session: Session, engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Return a TestClient whose database dependency serves the rollback-managed session."""

    # The lifespan startup guard opens its own session through the app.main indirection;
    # point it at the migration-built test engine so no test ever touches the dev DB.
    monkeypatch.setattr("app.main.SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))

    def override_get_db() -> Iterator[Session]:
        """Serve the shared transaction-managed session instead of a fresh one."""

        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
