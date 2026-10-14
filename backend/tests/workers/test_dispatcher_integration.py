"""Dispatcher integration tests against a real RabbitMQ broker on the rag_test vhost."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from kombu import Connection, Queue
from kombu.simple import SimpleQueue
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.outbox.events import (
    DOCUMENT_READY_FOR_EMBEDDING,
    EMBED_QUEUE,
    INGESTION_QUEUE,
    SOURCE_ITEM_INGESTION_REQUESTED,
)
from app.outbox.models import OutboxEvent
from app.workers.celery_app import make_celery_app
from app.workers.dispatcher import Backoff, BatchResult, dispatch_batch, run_loop
from tests.helpers import SettingsForTests

_DRAIN_TIMEOUT_SECONDS = 10.0
_BACKOFF = Backoff(base_seconds=1.0, max_seconds=300.0)
_PUBLISH_TIMEOUT_SECONDS = 10.0


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


def _dispatch(*, db: Session, app: Any, batch_size: int = 20) -> BatchResult:
    """Run one dispatch batch with the test backoff and publish timeout."""

    return dispatch_batch(
        db=db,
        app=app,
        batch_size=batch_size,
        backoff=_BACKOFF,
        publish_timeout_seconds=_PUBLISH_TIMEOUT_SECONDS,
    )


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


def test_backoff_delay_doubles_and_caps() -> None:
    """Check that the backoff doubles per attempt and caps at its maximum."""

    backoff = Backoff(base_seconds=1.0, max_seconds=300.0)
    assert backoff.delay_seconds(attempts=1) == 1.0
    assert backoff.delay_seconds(attempts=2) == 2.0
    assert backoff.delay_seconds(attempts=10) == 300.0


def test_dispatch_publishes_and_marks(*, db_session: Session, broker_url: str, purged_queues: None) -> None:
    """A dispatched ingestion event is published to the ingestion queue and marked published."""

    payload = _ingestion_payload()
    event = _seed_event(db=db_session, event_type=SOURCE_ITEM_INGESTION_REQUESTED, payload=payload)
    app = make_celery_app(broker_url=broker_url)
    assert _dispatch(db=db_session, app=app) == BatchResult(selected=1, published=1)
    db_session.refresh(event)
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
    assert _dispatch(db=db_session, app=app) == BatchResult(selected=1, published=1)
    task_name, kwargs = _drain_one(broker_url=broker_url, queue_name=EMBED_QUEUE)
    assert task_name == "embed_document"
    assert kwargs == payload


def test_publish_failure_backs_off_the_row(
    *, db_session: Session, broker_url: str, purged_queues: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed publish bumps attempts and pushes the row's next attempt into the future."""

    payload = _ingestion_payload()
    event = _seed_event(db=db_session, event_type=SOURCE_ITEM_INGESTION_REQUESTED, payload=payload)
    app = make_celery_app(broker_url=broker_url)

    def _failing_send_task(*args: object, **kwargs: object) -> None:
        """Stand-in for the app's publish path that simulates a broker outage."""

        raise RuntimeError("broker unreachable")

    with monkeypatch.context() as patcher:
        patcher.setattr(app, "send_task", _failing_send_task)
        assert _dispatch(db=db_session, app=app) == BatchResult(selected=1, published=0)
    db_session.refresh(event)
    assert event.attempts == 1
    assert event.last_error is not None
    assert "broker unreachable" in event.last_error
    assert event.published_at is None
    # The row's next attempt is one backoff interval past this transaction's now().
    assert event.next_attempt_at is not None
    assert event.next_attempt_at > event.created_at
    # Not due yet: an immediate second batch selects nothing.
    assert _dispatch(db=db_session, app=app) == BatchResult(selected=0, published=0)


def test_publish_failure_with_zero_backoff_retries_next_batch(
    *, db_session: Session, broker_url: str, purged_queues: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A zero backoff leaves the row due immediately, so the next batch publishes it."""

    payload = _ingestion_payload()
    event = _seed_event(db=db_session, event_type=SOURCE_ITEM_INGESTION_REQUESTED, payload=payload)
    app = make_celery_app(broker_url=broker_url)

    def _failing_send_task(*args: object, **kwargs: object) -> None:
        """Stand-in for the app's publish path that simulates a broker outage."""

        raise RuntimeError("broker unreachable")

    with monkeypatch.context() as patcher:
        patcher.setattr(app, "send_task", _failing_send_task)
        dispatch_batch(
            db=db_session,
            app=app,
            batch_size=20,
            backoff=Backoff(base_seconds=0.0, max_seconds=0.0),
            publish_timeout_seconds=_PUBLISH_TIMEOUT_SECONDS,
        )
    db_session.refresh(event)
    assert event.attempts == 1
    assert _dispatch(db=db_session, app=app) == BatchResult(selected=1, published=1)
    db_session.refresh(event)
    assert event.published_at is not None
    _drain_one(broker_url=broker_url, queue_name=INGESTION_QUEUE)


def test_backed_off_row_does_not_block_rows_behind_it(
    *, db_session: Session, broker_url: str, purged_queues: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backed-off oldest row cannot block the healthy rows behind it."""

    older = _seed_event(
        db=db_session, event_type=SOURCE_ITEM_INGESTION_REQUESTED, payload=_ingestion_payload()
    )
    newer = _seed_event(
        db=db_session, event_type=SOURCE_ITEM_INGESTION_REQUESTED, payload=_ingestion_payload()
    )
    # Explicit timestamps: the older row is selected and published first.
    older.next_attempt_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.flush()
    app = make_celery_app(broker_url=broker_url)

    calls = {"count": 0}

    def _failing_first_send_task(*args: object, **kwargs: object) -> None:
        """Fail only the first publish, simulating one bad broker moment."""

        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("broker unreachable")

    with monkeypatch.context() as patcher:
        patcher.setattr(app, "send_task", _failing_first_send_task)
        first = _dispatch(db=db_session, app=app)
    assert first == BatchResult(selected=2, published=0)

    second = _dispatch(db=db_session, app=app)
    assert second == BatchResult(selected=1, published=1)
    db_session.refresh(older)
    db_session.refresh(newer)
    assert older.published_at is None
    assert newer.published_at is not None
    task_name, kwargs = _drain_one(broker_url=broker_url, queue_name=INGESTION_QUEUE)
    assert task_name == "ingest_source_item"
    assert kwargs == newer.payload


def test_unroutable_rows_cannot_starve_the_outbox(
    *, db_session: Session, broker_url: str, purged_queues: None
) -> None:
    """More poison rows than one batch holds cannot starve the valid row behind them."""

    app = make_celery_app(broker_url=broker_url)
    now = datetime.now(UTC)
    poison = [
        _seed_event(db=db_session, event_type="not_a_real_event_type", payload={"junk": "true"})
        for _ in range(3)
    ]
    valid = _seed_event(
        db=db_session, event_type=SOURCE_ITEM_INGESTION_REQUESTED, payload=_ingestion_payload()
    )
    # Explicit timestamps: the poison rows are older than the valid row, so they are first.
    for offset, row in enumerate(poison):
        row.next_attempt_at = now - timedelta(hours=3 - offset)
    db_session.flush()

    first = _dispatch(db=db_session, app=app, batch_size=2)
    assert first == BatchResult(selected=2, published=0)
    second = _dispatch(db=db_session, app=app, batch_size=2)
    assert second == BatchResult(selected=2, published=1)

    db_session.refresh(valid)
    assert valid.published_at is not None
    for row in poison:
        db_session.refresh(row)
        assert row.attempts >= 1
        assert row.published_at is None
    task_name, kwargs = _drain_one(broker_url=broker_url, queue_name=INGESTION_QUEUE)
    assert task_name == "ingest_source_item"
    assert kwargs == valid.payload


def test_missing_route_bumps_without_breaking(
    *, db_session: Session, broker_url: str, purged_queues: None
) -> None:
    """An unroutable event is backed off while a valid row in the same batch still publishes."""

    unknown = _seed_event(db=db_session, event_type="not_a_real_event_type", payload={"junk": "true"})
    payload = _ingestion_payload()
    valid = _seed_event(db=db_session, event_type=SOURCE_ITEM_INGESTION_REQUESTED, payload=payload)
    app = make_celery_app(broker_url=broker_url)
    assert _dispatch(db=db_session, app=app) == BatchResult(selected=2, published=1)
    db_session.refresh(unknown)
    db_session.refresh(valid)
    assert unknown.attempts == 1
    assert unknown.last_error is not None
    assert unknown.published_at is None
    assert valid.published_at is not None
    task_name, kwargs = _drain_one(broker_url=broker_url, queue_name=INGESTION_QUEUE)
    assert task_name == "ingest_source_item"
    assert kwargs == payload


def test_published_task_id_is_the_outbox_row_id(
    *, db_session: Session, broker_url: str, purged_queues: None
) -> None:
    """The published message's task id is the outbox row id it was driven from."""

    event = _seed_event(
        db=db_session, event_type=SOURCE_ITEM_INGESTION_REQUESTED, payload=_ingestion_payload()
    )
    app = make_celery_app(broker_url=broker_url)
    assert _dispatch(db=db_session, app=app) == BatchResult(selected=1, published=1)
    with Connection(broker_url) as connection:
        queue = SimpleQueue(connection.default_channel, INGESTION_QUEUE, no_ack=True)
        try:
            message = queue.get(block=True, timeout=_DRAIN_TIMEOUT_SECONDS)
            assert message.headers["id"] == str(event.id)
        finally:
            queue.close()


def test_loop_survives_a_failing_tick(
    *,
    db_session: Session,
    broker_url: str,
    purged_queues: None,
    settings: SettingsForTests,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failing first tick does not end the loop: the second tick publishes and stays ready."""

    event = _seed_event(
        db=db_session, event_type=SOURCE_ITEM_INGESTION_REQUESTED, payload=_ingestion_payload()
    )
    app = make_celery_app(broker_url=broker_url)
    ticks = {"count": 0}

    @contextmanager
    def _session_factory() -> Iterator[Session]:
        """Raise on the first tick, then serve the test's shared session."""

        ticks["count"] += 1
        if ticks["count"] == 1:
            raise OperationalError("SELECT 1", {}, ValueError("database is gone"))
        yield db_session

    run_loop(
        app=app,
        settings=settings,
        session_factory=_session_factory,
        sleep=_no_sleep,
        max_ticks=2,
    )
    db_session.refresh(event)
    assert event.published_at is not None
    captured = capsys.readouterr()
    assert captured.err.count("dispatcher ready") == 1


def _no_sleep(*_seconds: float) -> None:
    """Drop loop sleeps so tests never wait a poll interval."""

    return None


def test_loop_skips_sleep_after_a_full_batch(
    *, db_session: Session, broker_url: str, purged_queues: None
) -> None:
    """A full batch means more work waits, so the loop does not sleep before ticking again."""

    for _ in range(2):
        _seed_event(db=db_session, event_type=SOURCE_ITEM_INGESTION_REQUESTED, payload=_ingestion_payload())
    app = make_celery_app(broker_url=broker_url)
    settings = SettingsForTests(outbox_batch_size=2)
    sleeps: list[float] = []

    @contextmanager
    def _session_factory() -> Iterator[Session]:
        """Serve the test's shared session."""

        yield db_session

    run_loop(
        app=app,
        settings=settings,
        session_factory=_session_factory,
        sleep=sleeps.append,
        max_ticks=1,
    )
    assert sleeps == []
