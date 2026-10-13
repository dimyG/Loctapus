"""Tests that migrations build the schema the models expect."""

import os
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from alembic import command
from app.core.db import make_engine

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEST_URL = "postgresql+psycopg://rag:rag@localhost:5432/rag_test"


def test_identity_tables_exist(*, engine: Engine) -> None:
    """Check that migrations created every expected table."""

    with engine.connect() as conn:
        names = set(inspect(conn).get_table_names())
    assert {
        "users",
        "workspaces",
        "teams",
        "team_memberships",
        "projects",
        "project_team_roles",
        "revoked_tokens",
    } <= names


def test_ingestion_tables_exist(*, engine: Engine) -> None:
    """Check that migrations created the six S3 tables."""

    with engine.connect() as conn:
        names = set(inspect(conn).get_table_names())
    assert {
        "sources",
        "source_items",
        "documents",
        "chunks",
        "ingestion_runs",
        "outbox_events",
    } <= names


def test_vector_and_fulltext_indexes(*, engine: Engine) -> None:
    """Check that chunks carries the HNSW and GIN indexes and the outbox its partial index."""

    with engine.connect() as conn:
        chunk_defs = (
            conn.execute(text("SELECT indexdef FROM pg_indexes WHERE tablename = 'chunks'")).scalars().all()
        )
        outbox_defs = (
            conn.execute(text("SELECT indexdef FROM pg_indexes WHERE tablename = 'outbox_events'"))
            .scalars()
            .all()
        )
    assert any("USING hnsw (embedding vector_cosine_ops)" in definition for definition in chunk_defs)
    assert any("USING gin (search_vector)" in definition for definition in chunk_defs)
    assert any("published_at IS NULL" in definition for definition in outbox_defs)


def test_citext_email_case_insensitive(*, engine: Engine, db_session: Session) -> None:
    """Check that the migrated email column matches case-insensitively."""

    from app.identity.models import User

    db_session.add(User(email="Case@Example.com", password_hash="x"))
    db_session.flush()
    found = db_session.query(User).filter(User.email == "case@example.com").one()
    assert found.email == "Case@Example.com"


def test_single_head_revision() -> None:
    """Check that the migration graph has exactly one head revision."""

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert len(script.get_heads()) == 1


def test_upgrade_ignores_stray_database_url_env(*, engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check that a stray RAG_DATABASE_URL cannot redirect a configured migration run."""

    monkeypatch.setenv("RAG_DATABASE_URL", "postgresql+psycopg://rag:rag@no-such-host:5432/rag_poison")
    url = os.environ.get("RAG_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    # The engine fixture already migrated to head, so this is a no-op run.
    command.upgrade(config, "head")


def test_foreign_key_columns_are_indexed(*, engine: Engine) -> None:
    """Check that foreign key columns without a covering unique constraint are indexed."""

    # Postgres does not index foreign keys automatically; the composite uniques cover
    # team_memberships.team_id and project_team_roles.project_id as leading columns only.
    # Only each index's leading column proves an FK is served: a non-leading column of a
    # composite index does not serve lookups on that column alone.
    expected = {
        "workspaces": {"owner_user_id"},
        "teams": {"workspace_id"},
        "projects": {"workspace_id"},
        "team_memberships": {"user_id"},
        "project_team_roles": {"team_id"},
        "sources": {"project_id"},
        "chunks": {"project_id"},
        "ingestion_runs": {"document_id", "source_item_id"},
    }
    with engine.connect() as conn:
        insp = inspect(conn)
        for table, columns in expected.items():
            leading = {index["column_names"][0] for index in insp.get_indexes(table)}
            assert columns <= leading, f"{table}: {columns - leading} not indexed"


def test_migrations_downgrade_to_base(*, engine: Engine) -> None:
    """Check that downgrading to base drops every table and the citext and vector extensions."""

    url = os.environ.get("RAG_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    db_name = f"{url.rsplit('/', 1)[1]}_downgrade"
    scratch_url = f"{url.rsplit('/', 1)[0]}/{db_name}"

    admin = make_engine(database_url=admin_url).execution_options(isolation_level="AUTOCOMMIT")
    scratch = make_engine(database_url=scratch_url)
    try:
        # Drop a leftover database first so reruns after a failed run stay self-healing.
        _terminate_and_drop(admin=admin, db_name=db_name)
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))

        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", scratch_url)
        config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        command.upgrade(config, "head")
        command.downgrade(config, "base")

        with scratch.connect() as conn:
            # Alembic keeps its own (empty) version table after a downgrade to base.
            assert set(inspect(conn).get_table_names()) <= {"alembic_version"}
            extensions = conn.execute(text("SELECT extname FROM pg_extension")).scalars().all()
            assert "citext" not in extensions
            assert "vector" not in extensions
    finally:
        scratch.dispose()
        _terminate_and_drop(admin=admin, db_name=db_name)
        admin.dispose()


def test_0002_downgrade_backfills_is_personal(*, engine: Engine) -> None:
    """Check that the 0002 downgrade restores pre-0002 personal flags on existing rows."""

    url = os.environ.get("RAG_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    db_name = f"{url.rsplit('/', 1)[1]}_0002_backfill"
    scratch_url = f"{url.rsplit('/', 1)[0]}/{db_name}"

    admin = make_engine(database_url=admin_url).execution_options(isolation_level="AUTOCOMMIT")
    scratch = make_engine(database_url=scratch_url)
    try:
        # Drop a leftover database first so reruns after a failed run stay self-healing.
        _terminate_and_drop(admin=admin, db_name=db_name)
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))

        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", scratch_url)
        config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        command.upgrade(config, "head")

        # Two owner-shaped rows: the "Personal" pair stands for a workspace registered
        # before 0002 (pre-0002 code renamed nothing), the "Default" pair for one after.
        w1, w2 = uuid.uuid4(), uuid.uuid4()
        t1, t2 = uuid.uuid4(), uuid.uuid4()
        user_rows = [(uuid.uuid4(), "d1@example.com"), (uuid.uuid4(), "d2@example.com")]
        with scratch.connect() as conn:
            conn.execute(
                text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, 'h')"),
                [{"id": uid, "email": email} for uid, email in user_rows],
            )
            conn.execute(
                text("INSERT INTO workspaces (id, name, owner_user_id) VALUES (:id, :name, :owner)"),
                [
                    {"id": w1, "name": "Default", "owner": user_rows[0][0]},
                    {"id": w2, "name": "Personal", "owner": user_rows[1][0]},
                ],
            )
            conn.execute(
                text("INSERT INTO teams (id, workspace_id, name) VALUES (:id, :ws, :name)"),
                [
                    {"id": t1, "ws": w1, "name": "Default"},
                    {"id": t2, "ws": w2, "name": "Personal"},
                ],
            )
            conn.commit()
        command.downgrade(config, "0001")
        with scratch.connect() as conn:
            ws_rows = conn.execute(text("SELECT name, is_personal FROM workspaces")).all()
            team_rows = conn.execute(text("SELECT name, is_personal FROM teams")).all()
        ws_flags: dict[str, bool] = {str(row[0]): bool(row[1]) for row in ws_rows}
        team_flags: dict[str, bool] = {str(row[0]): bool(row[1]) for row in team_rows}
        assert ws_flags == {"Default": True, "Personal": True}
        assert team_flags == {"Default": True, "Personal": True}
    finally:
        scratch.dispose()
        _terminate_and_drop(admin=admin, db_name=db_name)
        admin.dispose()


def _terminate_and_drop(*, admin: Engine, db_name: str) -> None:
    """Kill open connections to ``db_name`` and drop the database."""

    with admin.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": db_name},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
