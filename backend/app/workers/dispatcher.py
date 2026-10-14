"""The outbox dispatcher: a standalone polling process, deliberately not Celery Beat.

Run as ``python -m app.workers.dispatcher``; every ``outbox_poll_interval_seconds`` it
publishes one batch of due outbox events to the broker through the ``app/outbox/events.py``
routing map. A failing row is backed off one exponential interval and skipped, so
poison and outages cannot starve the rows behind them.
"""

import logging
import sys
import time
from dataclasses import dataclass
from datetime import timedelta

from celery import Celery
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.db import session_scope
from app.outbox.events import EVENT_ROUTES
from app.outbox.models import OutboxEvent
from app.workers.celery_app import make_celery_app

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Backoff:
    """The capped exponential delay a failed row waits before its next attempt."""

    base_seconds: float
    max_seconds: float

    def delay_seconds(self, *, attempts: int) -> float:
        """Return the delay after ``attempts`` failed attempts, capped at the maximum."""

        delay = self.base_seconds * 2 ** (attempts - 1)
        return delay if delay < self.max_seconds else self.max_seconds


@dataclass(frozen=True)
class BatchResult:
    """One dispatch batch's outcome: how many rows were selected and published."""

    selected: int
    published: int


def _bump(*, row: OutboxEvent, error: str, backoff: Backoff) -> None:
    """Record one failed attempt on the row and back its next attempt off."""

    row.attempts += 1
    row.last_error = error
    row.next_attempt_at = func.now() + timedelta(seconds=backoff.delay_seconds(attempts=row.attempts))


def dispatch_batch(
    *,
    db: Session,
    app: Celery,
    batch_size: int,
    backoff: Backoff,
    publish_timeout_seconds: float,
) -> BatchResult:
    """Publish one batch of due outbox rows in a single short transaction.

    One transaction covers select, publish, mark, and commit, and nothing is held while
    the caller sleeps. Publishing under the row locks is what makes "mark published"
    crash-safe, and ``SKIP LOCKED`` lets overlapping dispatcher runs cooperate.
    ``published_at`` is set only after the confirmed publish - ``send_task`` blocks until
    the broker's ``basic.ack`` - so a crash in between re-publishes (duplicate) rather
    than losing the event. Every failure - unroutable rows included - is backed off and
    recorded, never dropped and never blocking the rows behind it.
    """

    rows = (
        db.execute(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None), OutboxEvent.next_attempt_at <= func.now())
            .order_by(OutboxEvent.next_attempt_at, OutboxEvent.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    selected = len(rows)
    published = 0
    for row in rows:
        route = EVENT_ROUTES.get(row.event_type)
        if route is None:
            # An unroutable event is poison, but it must not starve the rows behind it.
            _bump(row=row, error=f"no route for event_type {row.event_type!r}", backoff=backoff)
            continue
        try:
            # task_id tags the message with its outbox row id; the timeouts bound the
            # publish (and its broker confirmation) so a dead broker cannot hang a tick.
            app.send_task(
                route.task_name,
                kwargs=row.payload,
                queue=route.queue,
                task_id=str(row.id),
                timeout=publish_timeout_seconds,
                confirm_timeout=publish_timeout_seconds,
            )
        except Exception as exc:
            # The batch ends here: rows not yet published keep their state for the
            # next tick instead of retrying publishes in place under row locks.
            _bump(row=row, error=str(exc), backoff=backoff)
            break
        row.published_at = func.now()
        published += 1
    db.commit()
    return BatchResult(selected=selected, published=published)


def main() -> None:
    """Run the dispatch loop forever, one short batch per poll interval."""

    settings = get_settings()
    app = make_celery_app(broker_url=settings.broker_url)
    backoff = Backoff(
        base_seconds=settings.outbox_retry_base_seconds,
        max_seconds=settings.outbox_retry_max_seconds,
    )
    # stderr, flushed: the e2e webServer entry waits on this line, and piped Python
    # stdout is block-buffered, so an unflushed print may never arrive.
    print("dispatcher ready", file=sys.stderr, flush=True)
    while True:
        with session_scope() as db:
            dispatch_batch(
                db=db,
                app=app,
                batch_size=settings.outbox_batch_size,
                backoff=backoff,
                publish_timeout_seconds=settings.outbox_publish_timeout_seconds,
            )
        time.sleep(settings.outbox_poll_interval_seconds)


if __name__ == "__main__":
    main()
