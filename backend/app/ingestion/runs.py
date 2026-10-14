"""The run state machine: guarded transitions, ingestion requests, and the latest status.

No function here commits: callers own the transaction, so the service keeps its
commit-per-transition choreography while every allowed (from, to) pair lives in
exactly one place.
"""

from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import ScalarSelect, SQLColumnExpression, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.ingestion.models import IngestionRun
from app.ingestion.status import RunStatus
from app.outbox.events import enqueue_source_item_ingestion_requested

# The one place that names which run transitions exist; anything else is a bug.
_ALLOWED_TRANSITIONS: frozenset[tuple[RunStatus, RunStatus]] = frozenset(
    {
        (RunStatus.QUEUED, RunStatus.FETCHING),
        (RunStatus.FETCHING, RunStatus.PROCESSING),
        (RunStatus.PROCESSING, RunStatus.INDEXING),
        (RunStatus.PROCESSING, RunStatus.READY),
        (RunStatus.INDEXING, RunStatus.READY),
        (RunStatus.FETCHING, RunStatus.FAILED),
        (RunStatus.PROCESSING, RunStatus.FAILED),
        (RunStatus.INDEXING, RunStatus.FAILED),
    }
)


def _transition(
    *,
    db: Session,
    run_id: UUID,
    from_status: RunStatus,
    to_status: RunStatus,
    values: dict[str, object],
) -> bool:
    """Run one guarded run-status UPDATE, raising ValueError for an illegal pair first.

    Zero matched rows means a duplicate or stale delivery, which callers turn into a
    no-op; the pair check runs before any SQL so an illegal call touches nothing.
    """

    if (from_status, to_status) not in _ALLOWED_TRANSITIONS:
        raise ValueError(f"cannot move a run from {from_status.value!r} to {to_status.value!r}")
    result = db.execute(
        update(IngestionRun)
        .where(IngestionRun.id == run_id, IngestionRun.status == from_status.value)
        .values(status=to_status.value, **values)
    )
    # Session.execute is typed as Result, but DML returns a CursorResult, the one result
    # class whose typing carries rowcount.
    rowcount = cast(CursorResult[Any], result).rowcount
    return rowcount == 1


def request_ingestion(*, db: Session, source_item_id: UUID, raw_object_key: str, content_hash: str) -> UUID:
    """Add one queued run and its outbox event inside the caller's transaction."""

    run_id = uuid4()
    db.add(IngestionRun(id=run_id, source_item_id=source_item_id, status=RunStatus.QUEUED))
    enqueue_source_item_ingestion_requested(
        db=db,
        source_item_id=source_item_id,
        ingestion_run_id=run_id,
        raw_object_key=raw_object_key,
        content_hash=content_hash,
    )
    return run_id


def claim_run(*, db: Session, run_id: UUID) -> bool:
    """Move a queued run to fetching and stamp its started_at."""

    return _transition(
        db=db,
        run_id=run_id,
        from_status=RunStatus.QUEUED,
        to_status=RunStatus.FETCHING,
        values={"started_at": func.now()},
    )


def start_processing(*, db: Session, run_id: UUID) -> bool:
    """Move a fetching run to processing."""

    return _transition(
        db=db,
        run_id=run_id,
        from_status=RunStatus.FETCHING,
        to_status=RunStatus.PROCESSING,
        values={},
    )


def mark_indexing(*, db: Session, run_id: UUID, document_id: UUID) -> bool:
    """Move a processing run to indexing with its document id."""

    return _transition(
        db=db,
        run_id=run_id,
        from_status=RunStatus.PROCESSING,
        to_status=RunStatus.INDEXING,
        values={"document_id": document_id},
    )


def mark_ready(*, db: Session, run_id: UUID, expected: RunStatus, document_id: UUID | None = None) -> bool:
    """Move a processing or indexing run to ready, stamping finished_at."""

    values: dict[str, object] = {"finished_at": func.now()}
    if document_id is not None:
        values["document_id"] = document_id
    return _transition(
        db=db,
        run_id=run_id,
        from_status=expected,
        to_status=RunStatus.READY,
        values=values,
    )


def mark_failed(*, db: Session, run_id: UUID, expected: RunStatus, error: str) -> bool:
    """Move a fetching, processing, or indexing run to failed with the error and finished_at."""

    return _transition(
        db=db,
        run_id=run_id,
        from_status=expected,
        to_status=RunStatus.FAILED,
        values={"error": error, "finished_at": func.now()},
    )


def latest_run_status(*, source_item_id: SQLColumnExpression[UUID]) -> ScalarSelect[str]:
    """Return the correlated latest-run status lookup for one source item."""

    return (
        select(IngestionRun.status)
        .where(IngestionRun.source_item_id == source_item_id)
        .order_by(IngestionRun.created_at.desc(), IngestionRun.id.desc())
        .limit(1)
        .scalar_subquery()
    )
