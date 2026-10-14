"""Tests for the outbox event constants and enqueue helpers."""

from uuid import uuid4

from sqlalchemy.orm import Session

from app.ingestion.models import IngestionRun
from app.ingestion.runs import request_ingestion
from app.outbox.events import (
    DOCUMENT_READY_FOR_EMBEDDING,
    EMBED_QUEUE,
    EVENT_ROUTES,
    INGESTION_QUEUE,
    SOURCE_ITEM_INGESTION_REQUESTED,
    EventRoute,
    enqueue_document_ready_for_embedding,
    enqueue_source_item_ingestion_requested,
)
from app.outbox.models import OutboxEvent
from tests.factories import seed_project, seed_upload


def test_ingestion_requested_event_row(*, db_session: Session) -> None:
    """Check that the ingestion-requested helper stores the exact payload and starts unpublished."""

    source_item_id = uuid4()
    ingestion_run_id = uuid4()
    event = enqueue_source_item_ingestion_requested(
        db=db_session,
        source_item_id=source_item_id,
        ingestion_run_id=ingestion_run_id,
    )
    db_session.flush()
    # Refresh so the payload is read back from the database, not from the Python object.
    db_session.refresh(event)
    assert event.event_type == "source_item_ingestion_requested"
    assert event.aggregate_type == "source_item"
    assert event.aggregate_id == source_item_id
    assert event.payload == {"ingestion_run_id": str(ingestion_run_id)}
    assert event.published_at is None
    assert event.attempts == 0


def test_document_ready_event_row(*, db_session: Session) -> None:
    """Check that the document-ready helper stores the exact payload and starts unpublished."""

    document_id = uuid4()
    ingestion_run_id = uuid4()
    event = enqueue_document_ready_for_embedding(
        db=db_session,
        document_id=document_id,
        ingestion_run_id=ingestion_run_id,
    )
    db_session.flush()
    # Refresh so the payload is read back from the database, not from the Python object.
    db_session.refresh(event)
    assert event.event_type == "document_ready_for_embedding"
    assert event.aggregate_type == "document"
    assert event.aggregate_id == document_id
    assert event.payload == {
        "document_id": str(document_id),
        "ingestion_run_id": str(ingestion_run_id),
    }
    assert event.published_at is None
    assert event.attempts == 0


def test_routes_cover_both_events() -> None:
    """Check that the routing map sends each event type to its worker task and queue."""

    assert SOURCE_ITEM_INGESTION_REQUESTED == "source_item_ingestion_requested"
    assert DOCUMENT_READY_FOR_EMBEDDING == "document_ready_for_embedding"
    assert INGESTION_QUEUE == "ingestion"
    assert EMBED_QUEUE == "embed"
    assert {
        SOURCE_ITEM_INGESTION_REQUESTED: EventRoute(
            task_name="ingest_source_item",
            queue=INGESTION_QUEUE,
            payload_keys=frozenset({"ingestion_run_id"}),
        ),
        DOCUMENT_READY_FOR_EMBEDDING: EventRoute(
            task_name="embed_document",
            queue=EMBED_QUEUE,
            payload_keys=frozenset({"document_id", "ingestion_run_id"}),
        ),
    } == EVENT_ROUTES


def test_ingestion_requested_payload_carries_only_the_run_id(*, db_session: Session) -> None:
    """Check that the payload is only the run id and the run row pins the key and hash."""

    project_id = seed_project(db=db_session, email="payload-only@example.com")
    seeded = seed_upload(db=db_session, project_id=project_id)
    run_id = request_ingestion(
        db=db_session,
        source_item_id=seeded.source_item_id,
        raw_object_key="raw/extra/key/one.pdf",
        content_hash="extra-hash",
    )
    db_session.flush()

    run = db_session.get(IngestionRun, run_id)
    assert run is not None
    assert run.raw_object_key == "raw/extra/key/one.pdf"
    assert run.content_hash == "extra-hash"
    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.event_type == SOURCE_ITEM_INGESTION_REQUESTED,
            OutboxEvent.aggregate_id == seeded.source_item_id,
        )
        .all()
    )
    assert any(event.payload == {"ingestion_run_id": str(run_id)} for event in events)
    assert all(set(event.payload) == {"ingestion_run_id"} for event in events)
