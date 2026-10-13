"""Thin Celery tasks over the ingestion services, one per outbox event payload.

The parameter names equal the event payload keys, so the dispatcher publishes each
row's payload directly as task kwargs; the pipeline logic itself stays testable
without Celery in ``app/ingestion/service.py``.
"""

from uuid import UUID

from app.core.config import get_settings
from app.core.db import session_scope
from app.ingestion.service import embed_document as embed_document_service
from app.ingestion.service import ingest_source_item as ingest_source_item_service
from app.providers import get_embedding_provider, get_parser
from app.storage.service import StorageService
from app.workers.celery_app import celery_app


@celery_app.task(name="ingest_source_item")
def ingest_source_item(
    *,
    source_item_id: str,
    ingestion_run_id: str,
    raw_object_key: str,
    content_hash: str,
) -> None:
    """Ingest one queued run's file version end to end, recording the outcome on the run."""

    settings = get_settings()
    with session_scope() as db:
        ingest_source_item_service(
            db=db,
            source_item_id=UUID(source_item_id),
            ingestion_run_id=UUID(ingestion_run_id),
            raw_object_key=raw_object_key,
            content_hash=content_hash,
            storage=StorageService(settings=settings),
            parser=get_parser(settings=settings),
            settings=settings,
        )


@celery_app.task(name="embed_document")
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
