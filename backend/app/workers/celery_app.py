"""Celery app construction and the worker's startup signal handlers.

``make_celery_app`` is the broker twin of ``make_engine``: every environment (dev,
pytest, e2e) builds its app from its own ``broker_url`` vhost, while the module-level
``celery_app`` points at the dev vhost exactly as ``SessionLocal`` points at the dev
database.
"""

import logging
from typing import Any

from celery import Celery
from celery.signals import worker_init, worker_ready
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.db import session_scope
from app.ingestion.service import run_startup_checks
from app.providers import EmbeddingProvider, get_embedding_provider

_logger = logging.getLogger(__name__)


def make_celery_app(*, broker_url: str) -> Celery:
    """Return a Celery app bound to ``broker_url`` with late acks and publisher confirms.

    The app moves messages only - there is no result backend, because task outcomes
    live in Postgres on the ingestion runs.
    """

    app = Celery(broker=broker_url, include=["app.workers.tasks"])
    # Late acks re-deliver a task whose worker died mid-run, and publisher confirms
    # make send_task a real wait for the broker's basic.ack.
    app.conf.task_acks_late = True
    app.conf.broker_transport_options = {"confirm_publish": True}
    return app


celery_app = make_celery_app(broker_url=get_settings().broker_url)


def _refuse_to_boot(*, db: Session, embedding_provider: EmbeddingProvider) -> None:
    """Run the dimension guard and turn any failure into a SystemExit.

    Celery's signal dispatch catches and swallows plain ``Exception`` subclasses,
    which would leave a mismatched worker booted; ``SystemExit`` derives from
    ``BaseException`` and survives the dispatch.
    """

    try:
        run_startup_checks(db=db, embedding_provider=embedding_provider)
    except Exception as exc:
        raise SystemExit(str(exc)) from exc


@worker_init.connect
def run_worker_startup_checks(
    *,
    db: Session | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    **_kwargs: Any,
) -> None:
    """Run the startup dimension guard on the production wiring, refusing to boot on mismatch.

    ``db`` and ``embedding_provider`` default to the settings-selected provider on a
    ``session_scope`` session; tests inject the test database and fake providers to
    exercise the refusal path.
    """

    provider = embedding_provider
    if provider is None:
        provider = get_embedding_provider(settings=get_settings())
    if db is not None:
        _refuse_to_boot(db=db, embedding_provider=provider)
        return
    with session_scope() as session:
        _refuse_to_boot(db=session, embedding_provider=provider)


@worker_ready.connect
def _log_worker_ready(**_kwargs: Any) -> None:
    """Log the one ready line the e2e webServer entry waits for on stderr."""

    # WARNING, not INFO: the e2e worker entry starts at Celery's default log level.
    _logger.warning("celery worker ready")
