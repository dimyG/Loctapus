"""Apply alembic migrations to the settings-selected database.

Run as ``python scripts/migrate.py`` (the compose ``one-off-initialization``
service): the URL flows from ``RAG_DATABASE_URL`` through the app settings into
alembic's config explicitly, so ``alembic/env.py`` never reads the environment
and a failed migration exits non-zero for compose to gate on.
"""

import sys
from pathlib import Path

from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parent.parent
# The backend package must be importable no matter the caller's cwd.
sys.path.insert(0, str(BACKEND_DIR))
CONNECT_TIMEOUT_SECONDS = "5"


def _bounded_url(*, database_url: str) -> str:
    """Return ``database_url`` with a connect timeout so an unreachable host fails fast."""

    # Without a timeout libpq can hang for minutes on an unreachable host, which
    # would stall compose instead of letting the one-off service fail.
    url = make_url(database_url)
    if "connect_timeout" in url.query:
        return database_url
    bounded = url.update_query_dict({"connect_timeout": CONNECT_TIMEOUT_SECONDS})
    return bounded.render_as_string(hide_password=False)


def main() -> None:
    """Upgrade the settings-selected database to the migration head."""

    from alembic.config import Config

    from alembic import command
    from app.core.config import get_settings

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    database_url = _bounded_url(database_url=get_settings().database_url)
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
