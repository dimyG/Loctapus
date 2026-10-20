"""Row factories shared across the S3 and S4 test modules.

``seed_project`` and ``seed_upload`` write the pipeline's baseline rows directly,
with no storage calls, so tests that do not need Garage bytes pay nothing for them.
``seed_document_with_chunks`` skips even the run and outbox rows, so retrieval tests
seed nothing but the rows both retrieval legs actually read.
"""

import hashlib
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.identity.service import register_user
from app.ingestion.models import Chunk, Document
from app.ingestion.runs import request_ingestion
from app.providers.stub_embeddings import StubEmbeddingProvider
from app.sources.models import Source, SourceItem
from app.storage.service import build_raw_object_key


def seed_project(*, db: Session, email: str) -> UUID:
    """Register a user through the real service and return their default project id."""

    registration = register_user(db=db, email=email, password="password123")
    return registration.project.id


@dataclass(frozen=True)
class SeededUpload:
    """Identity of one seeded upload: its rows' ids, object key, and content hash."""

    source_id: UUID
    source_item_id: UUID
    ingestion_run_id: UUID
    raw_object_key: str
    content_hash: str


@dataclass(frozen=True)
class SeededDocument:
    """Identity of one seeded document: its item's id, the document id, and its chunk ids."""

    source_item_id: UUID
    document_id: UUID
    chunk_ids: list[UUID]


def seed_document_with_chunks(
    *,
    db: Session,
    project_id: UUID,
    chunk_texts: list[str],
    filename: str = "doc.pdf",
    embed: bool = True,
) -> SeededDocument:
    """Seed one document with chunks directly: no run, no outbox, no storage call.

    Embeddings come from the stub provider so both retrieval legs see the rows.
    The caller owns the transaction: nothing is committed here. ``filename`` must
    stay unique inside the project per call, exactly as the uploads API guarantees.
    """

    source_id = db.scalar(select(Source.id).where(Source.project_id == project_id, Source.type == "upload"))
    if source_id is None:
        source = Source(project_id=project_id, type="upload")
        db.add(source)
        db.flush()
        source_id = source.id
    item_id = uuid4()
    content_hash = hashlib.sha256("".join(chunk_texts).encode("utf-8")).hexdigest()
    item = SourceItem(
        id=item_id,
        source_id=source_id,
        project_id=project_id,
        external_id=filename,
        filename=filename,
        content_type="application/octet-stream",
        size_bytes=sum(len(text) for text in chunk_texts),
        content_hash=content_hash,
        raw_object_key=build_raw_object_key(
            project_id=project_id,
            source_item_id=item_id,
            content_hash=content_hash,
            filename=filename,
        ),
    )
    document_id = uuid4()
    document = Document(
        id=document_id,
        source_item_id=item_id,
        project_id=project_id,
        content_hash=content_hash,
        raw_object_key=item.raw_object_key,
        normalized_content={},
    )
    embeddings = StubEmbeddingProvider().embed_documents(texts=chunk_texts) if embed else None
    # The unit of work orders INSERTs of unrelated mappers by table name, so each
    # FK level flushes before its dependents: source_items, then documents, then chunks.
    db.add(item)
    db.flush()
    db.add(document)
    db.flush()
    chunk_ids: list[UUID] = []
    for position, text in enumerate(chunk_texts):
        chunk_id = uuid4()
        chunk_ids.append(chunk_id)
        db.add(
            Chunk(
                id=chunk_id,
                project_id=project_id,
                document_id=document_id,
                position=position,
                text=text,
                heading_path=[],
                chunk_type="text",
                chunk_metadata={"filename": filename},
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                embedding=None if embeddings is None else embeddings[position],
            )
        )
    db.flush()
    return SeededDocument(source_item_id=item_id, document_id=document_id, chunk_ids=chunk_ids)


def seed_upload(
    *,
    db: Session,
    project_id: UUID,
    filename: str = "doc.pdf",
    content: bytes = b"%PDF-stub",
) -> SeededUpload:
    """Seed one upload's source, item, and queued run directly, with no storage call.

    The caller stores ``content`` under the returned ``raw_object_key`` when a test
    needs real bytes in Garage. Rows flush in FK order because the unit of work
    orders INSERTs of unrelated mappers by table name. The item reuses the project's
    one upload source, creating it when missing, exactly as the uploads API does.
    """

    source_id = db.scalar(select(Source.id).where(Source.project_id == project_id, Source.type == "upload"))
    if source_id is None:
        source = Source(project_id=project_id, type="upload")
        db.add(source)
        db.flush()
        source_id = source.id
    content_hash = hashlib.sha256(content).hexdigest()
    item_id = uuid4()
    raw_object_key = build_raw_object_key(
        project_id=project_id,
        source_item_id=item_id,
        content_hash=content_hash,
        filename=filename,
    )
    item = SourceItem(
        id=item_id,
        source_id=source_id,
        project_id=project_id,
        external_id=filename,
        filename=filename,
        content_type="application/octet-stream",
        size_bytes=len(content),
        content_hash=content_hash,
        raw_object_key=raw_object_key,
    )
    db.add(item)
    db.flush()
    run_id = request_ingestion(
        db=db, source_item_id=item_id, raw_object_key=raw_object_key, content_hash=content_hash
    )
    db.commit()
    return SeededUpload(
        source_id=source_id,
        source_item_id=item_id,
        ingestion_run_id=run_id,
        raw_object_key=raw_object_key,
        content_hash=content_hash,
    )
