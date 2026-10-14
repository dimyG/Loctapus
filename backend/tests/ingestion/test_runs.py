"""Tests for the run state machine in ingestion.runs and the status vocabulary."""

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ingestion.models import Document, IngestionRun
from app.ingestion.runs import (
    claim_run,
    latest_run_status,
    mark_failed,
    mark_indexing,
    mark_ready,
    request_ingestion,
    start_processing,
)
from app.ingestion.status import RunStatus
from app.outbox.events import SOURCE_ITEM_INGESTION_REQUESTED
from app.outbox.models import OutboxEvent
from app.sources.models import SourceItem
from app.sources.service import list_uploads
from tests.factories import seed_project, seed_upload

TIE_BREAK_TIME = datetime(2026, 10, 14, 12, 0, 0, tzinfo=UTC)


def test_status_enum_matches_the_migrated_check(*, engine: Engine) -> None:
    """Check that the migrated status check constraint names exactly the RunStatus values."""

    with engine.connect() as conn:
        definitions = (
            conn.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid = 'ingestion_runs'::regclass AND contype = 'c'"
                )
            )
            .scalars()
            .all()
        )
    # Postgres renders IN checks as "= ANY (ARRAY[...])", so pick the constraint by a
    # value only the status vocabulary contains.
    status_check = next(definition for definition in definitions if "'queued'" in definition)
    literals = set(re.findall(r"'([^']*)'", status_check))
    assert literals == {status.value for status in RunStatus}


def test_disallowed_transition_raises_without_touching_the_row(*, db_session: Session) -> None:
    """Check that an illegal transition raises ValueError and leaves the run untouched."""

    project_id = seed_project(db=db_session, email="runs-disallowed@example.com")
    seeded = seed_upload(db=db_session, project_id=project_id)

    with pytest.raises(ValueError):
        mark_failed(db=db_session, run_id=seeded.ingestion_run_id, expected=RunStatus.QUEUED, error="no")

    db_session.expire_all()
    run = db_session.get(IngestionRun, seeded.ingestion_run_id)
    assert run is not None
    assert run.status == RunStatus.QUEUED


def test_transitions_follow_the_pipeline(*, db_session: Session) -> None:
    """Check the guarded pipeline transitions and that a claimed run cannot be re-claimed."""

    project_id = seed_project(db=db_session, email="runs-pipeline@example.com")
    seeded = seed_upload(db=db_session, project_id=project_id)
    document = Document(
        source_item_id=seeded.source_item_id,
        project_id=project_id,
        content_hash="runs-pipeline-hash",
        raw_object_key=seeded.raw_object_key,
        normalized_content={"title": None, "elements": [], "metadata": {}},
    )
    db_session.add(document)
    db_session.flush()

    assert claim_run(db=db_session, run_id=seeded.ingestion_run_id) is True
    assert start_processing(db=db_session, run_id=seeded.ingestion_run_id) is True
    assert mark_indexing(db=db_session, run_id=seeded.ingestion_run_id, document_id=document.id) is True
    assert mark_ready(db=db_session, run_id=seeded.ingestion_run_id, expected=RunStatus.INDEXING) is True
    assert claim_run(db=db_session, run_id=seeded.ingestion_run_id) is False

    db_session.expire_all()
    run = db_session.get(IngestionRun, seeded.ingestion_run_id)
    assert run is not None
    assert run.status == RunStatus.READY
    assert run.started_at is not None
    assert run.finished_at is not None
    assert run.document_id == document.id


def test_finished_at_must_match_a_terminal_status(*, db_session: Session) -> None:
    """Check that a terminal status without finished_at is rejected on flush."""

    project_id = seed_project(db=db_session, email="runs-finished-at@example.com")
    seeded = seed_upload(db=db_session, project_id=project_id)

    run = db_session.get(IngestionRun, seeded.ingestion_run_id)
    assert run is not None
    run.status = RunStatus.READY
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_latest_run_status_prefers_the_newest_run(*, db_session: Session) -> None:
    """Check that the latest-run lookup orders by created_at and not by happenstance."""

    project_id = seed_project(db=db_session, email="runs-newest@example.com")
    seeded = seed_upload(db=db_session, project_id=project_id)
    base_time = datetime(2026, 10, 14, 12, 0, 0, tzinfo=UTC)
    db_session.execute(
        update(IngestionRun)
        .where(IngestionRun.id == seeded.ingestion_run_id)
        .values(status=RunStatus.FAILED, created_at=base_time, finished_at=base_time)
    )
    db_session.add(
        IngestionRun(
            id=uuid4(),
            source_item_id=seeded.source_item_id,
            status=RunStatus.QUEUED,
            raw_object_key="raw/newest/second/run.pdf",
            content_hash="newest-second-hash",
            created_at=base_time + timedelta(seconds=1),
        )
    )
    db_session.flush()

    status = db_session.execute(
        select(latest_run_status(source_item_id=SourceItem.id)).where(SourceItem.id == seeded.source_item_id)
    ).scalar_one()
    assert status == RunStatus.QUEUED


def test_latest_run_status_breaks_ties_by_id(*, db_session: Session) -> None:
    """Check that tied created_at resolves by id and the sources list stays one row."""

    project_id = seed_project(db=db_session, email="runs-tie@example.com")
    seeded = seed_upload(db=db_session, project_id=project_id)
    db_session.delete(db_session.get(IngestionRun, seeded.ingestion_run_id))
    db_session.add_all(
        [
            IngestionRun(
                id=UUID(int=1),
                source_item_id=seeded.source_item_id,
                status=RunStatus.FAILED,
                raw_object_key="raw/tie/first/run.pdf",
                content_hash="tie-first-hash",
                created_at=TIE_BREAK_TIME,
                finished_at=TIE_BREAK_TIME,
            ),
            IngestionRun(
                id=UUID(int=2),
                source_item_id=seeded.source_item_id,
                status=RunStatus.READY,
                raw_object_key="raw/tie/second/run.pdf",
                content_hash="tie-second-hash",
                created_at=TIE_BREAK_TIME,
                finished_at=TIE_BREAK_TIME,
            ),
        ]
    )
    db_session.flush()

    status = db_session.execute(
        select(latest_run_status(source_item_id=SourceItem.id)).where(SourceItem.id == seeded.source_item_id)
    ).scalar_one()
    assert status == RunStatus.READY

    rows = list_uploads(db=db_session, project_id=project_id)
    assert len(rows) == 1
    assert rows[0].status == RunStatus.READY


def test_request_ingestion_adds_a_queued_run_and_its_event(*, db_session: Session) -> None:
    """Check that request_ingestion appends one queued run and its outbox event."""

    project_id = seed_project(db=db_session, email="runs-request@example.com")
    seeded = seed_upload(db=db_session, project_id=project_id)

    run_id = request_ingestion(
        db=db_session,
        source_item_id=seeded.source_item_id,
        raw_object_key="raw/extra/key/report.pdf",
        content_hash="extra-hash",
    )
    db_session.flush()

    run = db_session.get(IngestionRun, run_id)
    assert run is not None
    assert run.status == RunStatus.QUEUED
    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.event_type == SOURCE_ITEM_INGESTION_REQUESTED,
            OutboxEvent.aggregate_id == seeded.source_item_id,
        )
        .all()
    )
    assert len(events) == 2
    assert any(event.payload["ingestion_run_id"] == str(run_id) for event in events)
