"""Thin Celery tasks over the ingestion services, one per outbox event payload.

The parameter names equal the event payload keys, so the dispatcher publishes each
row's payload directly as task kwargs; the pipeline logic itself stays testable
without Celery in ``app/ingestion/service.py``.
"""

from uuid import UUID

from sqlalchemy.exc import InterfaceError, OperationalError

from app.core.config import get_settings
from app.core.db import session_scope
from app.ingestion.service import embed_document as embed_document_service
from app.ingestion.service import ingest_source_item as ingest_source_item_service
from app.outbox.events import EMBED_DOCUMENT_TASK, INGEST_SOURCE_ITEM_TASK
from app.providers import get_embedding_provider, get_parser
from app.storage.service import get_storage
from app.workers.celery_app import celery_app

# Transient database failures (a restarted Postgres, a dropped pooled connection)
# autoretry with capped exponential backoff; every other failure ends on the run row.
_TASK_RETRY = {
    "autoretry_for": (OperationalError, InterfaceError),
    "retry_backoff": True,
    "retry_backoff_max": 60,
    "retry_jitter": True,
    "max_retries": 5,
}


@celery_app.task(name=INGEST_SOURCE_ITEM_TASK, **_TASK_RETRY)
def ingest_source_item(*, ingestion_run_id: str) -> None:
    """Ingest one queued run's pinned file version end to end, recording the outcome on the run."""

    settings = get_settings()
    with session_scope() as db:
        ingest_source_item_service(
            db=db,
            ingestion_run_id=UUID(ingestion_run_id),
            storage=get_storage(),
            parser=get_parser(settings=settings),
            settings=settings,
        )


@celery_app.task(name=EMBED_DOCUMENT_TASK, **_TASK_RETRY)
def embed_document(*, document_id: str, ingestion_run_id: str) -> None:
    """Embed one document's chunks in batches and move its run to ready."""

    settings = get_settings()
    with session_scope() as db:
        embed_document_service(
            db=db,
            document_id=UUID(document_id),
            ingestion_run_id=UUID(ingestion_run_id),
            embedding_provider=get_embedding_provider(settings=settings),
            settings=settings,
        )
