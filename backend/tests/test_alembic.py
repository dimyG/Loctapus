"""Tests that migrations build the schema the models expect."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parent.parent


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


def test_foreign_key_columns_are_indexed(*, engine: Engine) -> None:
    """Check that foreign key columns without a covering unique constraint are indexed."""

    # Postgres does not index foreign keys automatically; the composite uniques cover
    # team_memberships.team_id and project_team_roles.project_id as leading columns only.
    expected = {
        "workspaces": {"owner_user_id"},
        "teams": {"workspace_id"},
        "projects": {"workspace_id"},
        "team_memberships": {"user_id"},
        "project_team_roles": {"team_id"},
    }
    with engine.connect() as conn:
        insp = inspect(conn)
        for table, columns in expected.items():
            indexed = {col for index in insp.get_indexes(table) for col in index["column_names"]}
            assert columns <= indexed, f"{table}: {columns - indexed} not indexed"
