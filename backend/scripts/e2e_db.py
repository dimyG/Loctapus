"""E2E database lifecycle for the browser suite.

Bootstrap recreates the dedicated ``rag_e2e`` database through migrations and
provisions its ``rag_e2e`` broker vhost (mirroring ``tests/conftest.py``);
truncate empties every domain table so each Playwright test starts from a
clean state. Run from anywhere::

    python scripts/e2e_db.py bootstrap
    python scripts/e2e_db.py truncate
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
# The backend package must be importable no matter the caller's cwd.
sys.path.insert(0, str(BACKEND_DIR))

E2E_URL = "postgresql+psycopg://rag:rag@localhost:5432/rag_e2e"
# Broker isolation mirrors the database: without its own vhost a running dev
# worker would consume the e2e run's ingestion messages and hang the journey.
BROKER_URL = "amqp://guest:guest@localhost:5672/rag_e2e"
ADMIN_URL = E2E_URL.rsplit("/", 1)[0] + "/postgres"
DB_NAME = E2E_URL.rsplit("/", 1)[1]


def bootstrap() -> None:
    """Recreate ``rag_e2e`` from scratch, migrate it to head, and ensure its vhost."""

    # Imported lazily so the sys.path setup above precedes the app import.
    from alembic.config import Config
    from sqlalchemy import text

    from alembic import command
    from app.core.db import make_engine
    from scripts.broker_admin import ensure_broker_vhost

    admin = make_engine(database_url=ADMIN_URL).execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": DB_NAME},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{DB_NAME}"'))
        conn.execute(text(f'CREATE DATABASE "{DB_NAME}"'))
    admin.dispose()

    # Both management-API calls are idempotent, so repeated bootstraps are safe.
    ensure_broker_vhost(broker_url=BROKER_URL)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", E2E_URL)
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")


def truncate() -> None:
    """Empty every domain table, restarting identity columns."""

    from sqlalchemy import text

    from app.core.db import make_engine

    engine = make_engine(database_url=E2E_URL)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE users, workspaces, teams, team_memberships, "
                "projects, project_team_roles, revoked_tokens, "
                "sources, source_items, documents, chunks, ingestion_runs, outbox_events "
                "RESTART IDENTITY CASCADE"
            )
        )
    engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"bootstrap", "truncate"}:
        raise SystemExit("usage: e2e_db.py {bootstrap|truncate}")
    if sys.argv[1] == "bootstrap":
        bootstrap()
    else:
        truncate()
