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
