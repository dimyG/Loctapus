"""The outbox dispatcher: a standalone polling process, deliberately not Celery Beat.

Run as ``python -m app.workers.dispatcher``; every ``outbox_poll_interval_seconds``
it publishes one batch of committed outbox events to the broker through the
``app/outbox/events.py`` routing map.
"""

import sys
import time

from celery import Celery
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.db import session_scope
from app.outbox.events import EVENT_ROUTES
from app.outbox.models import OutboxEvent
from app.workers.celery_app import make_celery_app


def _bump(*, row: OutboxEvent, error: str) -> None:
    """Record one failed attempt on the row so the next tick retries it."""

    row.attempts += 1
    row.last_error = error


def dispatch_batch(*, db: Session, app: Celery, batch_size: int) -> int:
    """Publish one batch of unpublished outbox rows in a single short transaction.

    One transaction covers select, publish, mark, and commit, and nothing is held
    while the caller sleeps. Publishing under the row locks is what makes "mark
    published" crash-safe, and ``SKIP LOCKED`` lets overlapping dispatcher runs
    cooperate. ``published_at`` is set only after the confirmed publish - ``send_task``
    blocks until the broker's ``basic.ack`` - so a crash in between re-publishes
    (duplicate) rather than losing the event.
    """

    rows = (
        db.execute(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    published = 0
    for row in rows:
        route = EVENT_ROUTES.get(row.event_type)
        if route is None:
            # An unroutable event is poison, but it must not starve the rows behind it.
            _bump(row=row, error=f"no route for event_type {row.event_type!r}")
            continue
        try:
            app.send_task(route.task_name, kwargs=row.payload, queue=route.queue)
        except Exception as exc:
            # The batch ends here: rows not yet published keep their state for the
            # next tick instead of retrying publishes in place under row locks.
            _bump(row=row, error=str(exc))
            break
        row.published_at = func.now()
        published += 1
    db.commit()
    return published


def main() -> None:
    """Run the dispatch loop forever, one short batch per poll interval."""

    settings = get_settings()
    app = make_celery_app(broker_url=settings.broker_url)
    # stderr, flushed: the e2e webServer entry waits on this line, and piped Python
    # stdout is block-buffered, so an unflushed print may never arrive.
    print("dispatcher ready", file=sys.stderr, flush=True)
    while True:
        with session_scope() as db:
            dispatch_batch(db=db, app=app, batch_size=settings.outbox_batch_size)
        time.sleep(settings.outbox_poll_interval_seconds)


if __name__ == "__main__":
    main()
