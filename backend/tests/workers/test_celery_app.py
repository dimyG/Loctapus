"""Tests for Celery app construction and the worker startup signal handlers."""

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.outbox.events import EMBED_DOCUMENT_TASK, INGEST_SOURCE_ITEM_TASK
from app.providers import get_embedding_provider
from app.workers.celery_app import celery_app, make_celery_app
from app.workers.signals import run_worker_startup_checks
from tests.fakes import MismatchedEmbeddingProvider

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def test_make_celery_app_configures_broker_and_acks() -> None:
    """The app binds the broker, late acks, publisher confirms, and no result backend."""

    app = make_celery_app(broker_url="amqp://guest:guest@localhost:5672/rag_test")
    assert app.conf.broker_url == "amqp://guest:guest@localhost:5672/rag_test"
    assert app.conf.task_acks_late is True
    assert app.conf.broker_transport_options["confirm_publish"] is True
    # The stubs type result_backend as str, but the real default (and our config) is None.
    result_backend: object = app.conf.result_backend
    assert result_backend is None


def test_worker_init_refuses_on_dimension_mismatch(*, db_session: Session) -> None:
    """The handler turns a dimension mismatch into a SystemExit naming both numbers."""

    provider = MismatchedEmbeddingProvider(dimension=512)
    with pytest.raises(SystemExit) as excinfo:
        run_worker_startup_checks(db=db_session, embedding_provider=provider)
    message = str(excinfo.value)
    assert "384" in message
    assert "512" in message
    assert "Alembic migration" in message


def test_worker_init_passes_with_stub(*, db_session: Session, settings: Settings) -> None:
    """The handler lets the settings-selected stub provider boot against the catalog."""

    provider = get_embedding_provider(settings=settings)
    run_worker_startup_checks(db=db_session, embedding_provider=provider)


def test_tasks_retry_transient_database_errors() -> None:
    """Both pipeline tasks autoretry on transient database errors, capped at five."""

    from typing import Any

    from sqlalchemy.exc import InterfaceError, OperationalError

    celery_app.loader.import_default_modules()
    for task_name in (INGEST_SOURCE_ITEM_TASK, EMBED_DOCUMENT_TASK):
        # autoretry_for and the retry knobs are runtime attributes the Celery
        # stubs do not declare.
        task: Any = celery_app.tasks[task_name]
        assert OperationalError in task.autoretry_for
        assert InterfaceError in task.autoretry_for
        assert task.max_retries == 5
        assert task.retry_backoff_max == 60


def test_dispatcher_does_not_import_the_pipeline() -> None:
    """Importing the dispatcher must not pull the ingestion pipeline or its parsers."""

    code = (
        "import sys, app.workers.dispatcher; "
        "assert 'app.ingestion.service' not in sys.modules; "
        "assert 'pypdf' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, check=True)


def test_worker_init_refuses_when_provider_resolution_fails(
    *, db_session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider that cannot be resolved refuses boot instead of starting a worker."""

    provider = get_embedding_provider(settings=settings)

    def _exploding_get_parser(*, settings: Settings) -> object:
        """Stand-in for the settings-driven parser factory."""

        raise ValueError("no such parser")

    monkeypatch.setattr("app.workers.signals.get_parser", _exploding_get_parser)
    with pytest.raises(SystemExit):
        run_worker_startup_checks(db=db_session, embedding_provider=provider)


def test_celery_app_declares_both_queues() -> None:
    """The app declares both durable queues and defaults new tasks to ingestion."""

    app = make_celery_app(broker_url="amqp://guest:guest@localhost:5672/rag_test")
    queues = {queue.name: queue for queue in app.conf.task_queues}
    assert set(queues) == {"ingestion", "embed"}
    assert all(queue.durable for queue in queues.values())
    assert app.conf.task_default_queue == "ingestion"
    assert app.conf.broker_connection_retry_on_startup is True
    assert app.conf.include == ["app.workers.tasks", "app.workers.signals"]
