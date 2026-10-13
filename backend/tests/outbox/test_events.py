"""Tests for the outbox event constants and enqueue helpers."""

from uuid import uuid4

from sqlalchemy.orm import Session

from app.outbox.events import (
    DOCUMENT_READY_FOR_EMBEDDING,
    EMBED_QUEUE,
    EVENT_ROUTES,
    INGESTION_QUEUE,
    SOURCE_ITEM_INGESTION_REQUESTED,
    enqueue_document_ready_for_embedding,
    enqueue_source_item_ingestion_requested,
)


def test_ingestion_requested_event_row(*, db_session: Session) -> None:
    """Check that the ingestion-requested helper stores the exact payload and starts unpublished."""

    source_item_id = uuid4()
    ingestion_run_id = uuid4()
    event = enqueue_source_item_ingestion_requested(
        db=db_session,
        source_item_id=source_item_id,
        ingestion_run_id=ingestion_run_id,
        raw_object_key="raw/p1/i1/abc123/report.pdf",
        content_hash="abc123",
    )
    db_session.flush()
    # Refresh so the payload is read back from the database, not from the Python object.
    db_session.refresh(event)
    assert event.event_type == "source_item_ingestion_requested"
    assert event.aggregate_type == "source_item"
    assert event.aggregate_id == source_item_id
    assert event.payload == {
        "source_item_id": str(source_item_id),
        "ingestion_run_id": str(ingestion_run_id),
        "raw_object_key": "raw/p1/i1/abc123/report.pdf",
        "content_hash": "abc123",
    }
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
    assert EVENT_ROUTES == {
        SOURCE_ITEM_INGESTION_REQUESTED: ("ingest_source_item", INGESTION_QUEUE),
        DOCUMENT_READY_FOR_EMBEDDING: ("embed_document", EMBED_QUEUE),
    }
