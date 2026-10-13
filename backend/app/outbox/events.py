"""Outbox event constants, task routing, and the enqueue helpers that append events."""

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.orm import Session

from app.outbox.models import OutboxEvent

SOURCE_ITEM_INGESTION_REQUESTED = "source_item_ingestion_requested"
DOCUMENT_READY_FOR_EMBEDDING = "document_ready_for_embedding"

# Queue names live here so the API process never imports the workers module.
INGESTION_QUEUE = "ingestion"
EMBED_QUEUE = "embed"

# Event type to (worker task name, queue); the dispatcher routes published events by this map.
EVENT_ROUTES: Mapping[str, tuple[str, str]] = {
    SOURCE_ITEM_INGESTION_REQUESTED: ("ingest_source_item", INGESTION_QUEUE),
    DOCUMENT_READY_FOR_EMBEDDING: ("embed_document", EMBED_QUEUE),
}


def enqueue_source_item_ingestion_requested(
    *,
    db: Session,
    source_item_id: UUID,
    ingestion_run_id: UUID,
    raw_object_key: str,
    content_hash: str,
) -> OutboxEvent:
    """Append a source-item ingestion-requested event inside the caller's transaction."""

    event = OutboxEvent(
        event_type=SOURCE_ITEM_INGESTION_REQUESTED,
        aggregate_type="source_item",
        aggregate_id=source_item_id,
        # Payload values are JSON strings so workers decode them without UUID coercion.
        payload={
            "source_item_id": str(source_item_id),
            "ingestion_run_id": str(ingestion_run_id),
            "raw_object_key": raw_object_key,
            "content_hash": content_hash,
        },
    )
    db.add(event)
    return event


def enqueue_document_ready_for_embedding(
    *, db: Session, document_id: UUID, ingestion_run_id: UUID
) -> OutboxEvent:
    """Append a document-ready-for-embedding event inside the caller's transaction."""

    event = OutboxEvent(
        event_type=DOCUMENT_READY_FOR_EMBEDDING,
        aggregate_type="document",
        aggregate_id=document_id,
        payload={"document_id": str(document_id), "ingestion_run_id": str(ingestion_run_id)},
    )
    db.add(event)
    return event
