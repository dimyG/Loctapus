"""Outbox event constants, payload contracts, task routing, and the enqueue helpers.

Task names and payload keys live here so the task decorators, the routing map, and the
published kwargs cannot drift apart.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import NamedTuple, TypedDict
from uuid import UUID

from sqlalchemy.orm import Session

from app.outbox.models import OutboxEvent

SOURCE_ITEM_INGESTION_REQUESTED = "source_item_ingestion_requested"
DOCUMENT_READY_FOR_EMBEDDING = "document_ready_for_embedding"

# Queue names live here so the API process never imports the workers module.
INGESTION_QUEUE = "ingestion"
EMBED_QUEUE = "embed"

# Task names live here so the decorators and the routing map name each task once.
INGEST_SOURCE_ITEM_TASK = "ingest_source_item"
EMBED_DOCUMENT_TASK = "embed_document"


class IngestionRequestedPayload(TypedDict):
    """The kwargs of the ingest task: the id of the run that pins the file version."""

    ingestion_run_id: str


class DocumentReadyPayload(TypedDict):
    """The kwargs of the embed task."""

    document_id: str
    ingestion_run_id: str


class EventRoute(NamedTuple):
    """Where one event type is published: its task, its queue, and its payload keys."""

    task_name: str
    queue: str
    payload_keys: frozenset[str]


EVENT_ROUTES: Mapping[str, EventRoute] = MappingProxyType(
    {
        SOURCE_ITEM_INGESTION_REQUESTED: EventRoute(
            task_name=INGEST_SOURCE_ITEM_TASK,
            queue=INGESTION_QUEUE,
            payload_keys=frozenset(IngestionRequestedPayload.__annotations__),
        ),
        DOCUMENT_READY_FOR_EMBEDDING: EventRoute(
            task_name=EMBED_DOCUMENT_TASK,
            queue=EMBED_QUEUE,
            payload_keys=frozenset(DocumentReadyPayload.__annotations__),
        ),
    }
)


def enqueue_source_item_ingestion_requested(
    *,
    db: Session,
    source_item_id: UUID,
    ingestion_run_id: UUID,
) -> OutboxEvent:
    """Append a source-item ingestion-requested event inside the caller's transaction."""

    event = OutboxEvent(
        event_type=SOURCE_ITEM_INGESTION_REQUESTED,
        aggregate_type="source_item",
        aggregate_id=source_item_id,
        # The run row pins the file version; the payload carries the run id only, so
        # the worker reads its own version from the database instead of trusting a message.
        payload={"ingestion_run_id": str(ingestion_run_id)},
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
