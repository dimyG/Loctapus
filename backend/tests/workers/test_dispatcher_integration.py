"""Dispatcher integration tests against a real RabbitMQ broker on the rag_test vhost."""

from typing import Any
from uuid import uuid4

import pytest
from kombu import Connection, Queue
from kombu.simple import SimpleQueue
from sqlalchemy.orm import Session

from app.outbox.events import (
    DOCUMENT_READY_FOR_EMBEDDING,
    EMBED_QUEUE,
    INGESTION_QUEUE,
    SOURCE_ITEM_INGESTION_REQUESTED,
)
from app.outbox.models import OutboxEvent
from app.workers.celery_app import make_celery_app
from app.workers.dispatcher import dispatch_batch

_DRAIN_TIMEOUT_SECONDS = 10.0


@pytest.fixture(scope="module")
def purged_queues(*, broker_url: str) -> None:
    """Declare then purge both worker queues so stale messages never leak into these tests."""

    with Connection(broker_url) as connection:
        channel = connection.default_channel
        for queue_name in (INGESTION_QUEUE, EMBED_QUEUE):
            queue = Queue(queue_name, channel=channel)
            queue.declare()
            queue.purge()


def _seed_event(*, db: Session, event_type: str, payload: dict[str, str]) -> OutboxEvent:
    """Add one outbox row inside the test's transaction and flush it."""

    event = OutboxEvent(
        event_type=event_type,
        aggregate_type="source_item",
        aggregate_id=uuid4(),
        payload=payload,
    )
    db.add(event)
    db.flush()
    return event


def _ingestion_payload() -> dict[str, str]:
    """Return one synthetic ingestion-requested payload shaped exactly like the enqueue helper's."""

    return {"ingestion_run_id": str(uuid4())}


def _drain_one(*, broker_url: str, queue_name: str) -> tuple[str, dict[str, Any]]:
    """Read exactly one task message off the named queue, returning its task name and kwargs."""

    with Connection(broker_url) as connection:
        # no_ack keeps a failed assertion from leaving an unacknowledged message behind.
        queue = SimpleQueue(connection.default_channel, queue_name, no_ack=True)
        try:
            message = queue.get(block=True, timeout=_DRAIN_TIMEOUT_SECONDS)
            # Protocol v2: the body is [args, kwargs, embed]; the task name rides in headers.
            task_name = message.headers["task"]
            kwargs: dict[str, Any] = message.payload[1]
        finally:
            queue.close()
    return task_name, kwargs


def test_dispatch_publishes_and_marks(*, db_session: Session, broker_url: str, purged_queues: None) -> None:
    """A dispatched ingestion event is published to the ingestion queue and marked published."""

    payload = _ingestion_payload()
    event = _seed_event(db=db_session, event_type=SOURCE_ITEM_INGESTION_REQUESTED, payload=payload)
    app = make_celery_app(broker_url=broker_url)
    assert dispatch_batch(db=db_session, app=app, batch_size=20) == 1
    assert event.published_at is not None
    task_name, kwargs = _drain_one(broker_url=broker_url, queue_name=INGESTION_QUEUE)
    assert task_name == "ingest_source_item"
    assert kwargs == payload


def test_dispatch_routes_embed_events_to_embed_queue(
    *, db_session: Session, broker_url: str, purged_queues: None
) -> None:
    """A document_ready_for_embedding event lands on the embed queue as embed_document."""

    payload = {"document_id": str(uuid4()), "ingestion_run_id": str(uuid4())}
    _seed_event(db=db_session, event_type=DOCUMENT_READY_FOR_EMBEDDING, payload=payload)
    app = make_celery_app(broker_url=broker_url)
    assert dispatch_batch(db=db_session, app=app, batch_size=20) == 1
    task_name, kwargs = _drain_one(broker_url=broker_url, queue_name=EMBED_QUEUE)
    assert task_name == "embed_document"
    assert kwargs == payload


def test_publish_failure_bumps_and_retries(
    *, db_session: Session, broker_url: str, purged_queues: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed publish bumps attempts and last_error, and the next batch publishes the row."""

    payload = _ingestion_payload()
    event = _seed_event(db=db_session, event_type=SOURCE_ITEM_INGESTION_REQUESTED, payload=payload)
    app = make_celery_app(broker_url=broker_url)

    def _failing_send_task(*args: object, **kwargs: object) -> None:
        """Stand-in for the app's publish path that simulates a broker outage."""

        raise RuntimeError("broker unreachable")

    with monkeypatch.context() as patcher:
        patcher.setattr(app, "send_task", _failing_send_task)
        assert dispatch_batch(db=db_session, app=app, batch_size=20) == 0
    assert event.attempts == 1
    assert event.last_error is not None
    assert "broker unreachable" in event.last_error
    assert event.published_at is None
    assert dispatch_batch(db=db_session, app=app, batch_size=20) == 1
    assert event.published_at is not None
    task_name, kwargs = _drain_one(broker_url=broker_url, queue_name=INGESTION_QUEUE)
    assert task_name == "ingest_source_item"
    assert kwargs == payload


def test_missing_route_bumps_without_breaking(
    *, db_session: Session, broker_url: str, purged_queues: None
) -> None:
    """An unroutable event is bumped while a valid row in the same batch still publishes."""

    unknown = _seed_event(db=db_session, event_type="not_a_real_event_type", payload={"junk": "true"})
    payload = _ingestion_payload()
    valid = _seed_event(db=db_session, event_type=SOURCE_ITEM_INGESTION_REQUESTED, payload=payload)
    app = make_celery_app(broker_url=broker_url)
    assert dispatch_batch(db=db_session, app=app, batch_size=20) == 1
    assert unknown.attempts == 1
    assert unknown.last_error is not None
    assert unknown.published_at is None
    assert valid.published_at is not None
    task_name, kwargs = _drain_one(broker_url=broker_url, queue_name=INGESTION_QUEUE)
    assert task_name == "ingest_source_item"
    assert kwargs == payload
