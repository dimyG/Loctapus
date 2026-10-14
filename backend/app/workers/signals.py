"""The worker's startup and readiness signal handlers.

The handlers live in the ``include`` list, so Celery imports this module before it
boots the worker and the signals connect in time. They stay out of ``celery_app`` so
importing the app never drags the ingestion pipeline or the providers in.
"""

import logging
from typing import Any

from celery.signals import worker_init, worker_ready
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.db import engine, session_scope
from app.ingestion.schema_guard import run_startup_checks
from app.providers import EmbeddingProvider, get_embedding_provider, get_parser
from app.providers.base import Parser

_logger = logging.getLogger(__name__)


@worker_init.connect
def run_worker_startup_checks(
    *,
    db: Session | None = None,
    parser: Parser | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    **_kwargs: Any,
) -> None:
    """Run the startup checks on the production wiring, refusing to boot on any failure.

    Both providers resolve inside the ``SystemExit`` guard: Celery's signal dispatch
    catches and logs plain ``Exception`` subclasses, which would leave a half-booted
    worker running. ``db``, ``parser``, and ``embedding_provider`` default to the
    settings-selected wiring on a ``session_scope`` session; tests inject the test
    database and fakes to exercise the refusal paths.
    """

    settings = get_settings()
    try:
        # Resolving the parser is itself a boot check: an unresolvable provider must
        # refuse boot here, not crash the worker's first task.
        if parser is None:
            get_parser(settings=settings)
        resolved_provider = (
            embedding_provider
            if embedding_provider is not None
            else get_embedding_provider(settings=settings)
        )
        if db is None:
            with session_scope() as session:
                run_startup_checks(db=session, embedding_provider=resolved_provider)
            # No guard connection outlives boot; safe under prefork, where children
            # re-connect through their own pool.
            engine.dispose()
        else:
            run_startup_checks(db=db, embedding_provider=resolved_provider)
    except Exception as exc:
        raise SystemExit(str(exc)) from exc


@worker_ready.connect
def _log_worker_ready(**_kwargs: Any) -> None:
    """Log the one ready line the e2e webServer entry waits for on stderr."""

    # WARNING, not INFO: the e2e worker entry starts at Celery's default log level.
    _logger.warning("celery worker ready")
