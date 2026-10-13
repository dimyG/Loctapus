"""Tests for Celery app construction and the worker_init startup guard."""

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.providers import get_embedding_provider
from app.workers.celery_app import make_celery_app, run_worker_startup_checks


class _MismatchedEmbeddingProvider:
    """Embedding provider whose dimension disagrees with the migrated chunks.embedding column."""

    dimension: int

    def __init__(self, *, dimension: int) -> None:
        """Record the deliberately mismatching dimension."""

        self.dimension = dimension

    def embed_documents(self, *, texts: list[str]) -> list[list[float]]:
        """Return zero vectors of the declared dimension."""

        return [[0.0] * self.dimension for _ in texts]

    def embed_query(self, *, text: str) -> list[float]:
        """Return a zero vector of the declared dimension."""

        return [0.0] * self.dimension


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

    provider = _MismatchedEmbeddingProvider(dimension=512)
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
