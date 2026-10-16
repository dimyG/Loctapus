"""Tests for the compose one-off-initialization script."""

import os
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.db import make_engine
from tests.test_alembic import _terminate_and_drop

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEST_URL = "postgresql+psycopg://rag:rag@localhost:5432/rag_test"


def _head_revision() -> str:
    """Return the migration graph's single head revision."""

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return str(ScriptDirectory.from_config(config).get_current_head())


def _run_migrate(*, database_url: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the script as a real subprocess against ``database_url`` from ``cwd``."""

    env = {**os.environ, "RAG_DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, str(BACKEND_DIR / "scripts" / "migrate.py")],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_migrate_applies_head_from_any_cwd(*, tmp_path: Path) -> None:
    """Check that the script migrates a scratch database to head from outside backend/."""

    url = os.environ.get("RAG_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    db_name = f"{url.rsplit('/', 1)[1]}_migrate"
    scratch_url = f"{url.rsplit('/', 1)[0]}/{db_name}"

    admin = make_engine(database_url=admin_url).execution_options(isolation_level="AUTOCOMMIT")
    try:
        # Drop a leftover first so reruns after a failed run stay self-healing.
        _terminate_and_drop(admin=admin, db_name=db_name)
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))

        result = _run_migrate(database_url=scratch_url, cwd=tmp_path)
        assert result.returncode == 0, result.stderr

        scratch = make_engine(database_url=scratch_url)
        try:
            with scratch.connect() as conn:
                version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        finally:
            scratch.dispose()
        assert version == _head_revision()
    finally:
        _terminate_and_drop(admin=admin, db_name=db_name)
        admin.dispose()


def test_migrate_exits_nonzero_on_unreachable_database(*, tmp_path: Path) -> None:
    """Check that a failed migration exits non-zero - the status compose gates on."""

    result = _run_migrate(
        database_url="postgresql+psycopg://rag:rag@localhost:5433/rag_unreachable",
        cwd=tmp_path,
    )
    assert result.returncode != 0
