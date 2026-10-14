"""The ingest and embed pipeline services and the worker's embedding dimension guard.

Every run-status change is a conditional ``UPDATE ... WHERE id = :run_id AND
status = :expected`` so duplicate or stale deliveries can never clobber newer state,
and no transaction ever spans a storage or provider call.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.ingestion.chunking import ChunkText, chunk_elements
from app.ingestion.models import Chunk, Document
from app.ingestion.runs import claim_run, mark_failed, mark_indexing, mark_ready, start_processing
from app.ingestion.status import RunStatus
from app.outbox.events import enqueue_document_ready_for_embedding
from app.providers.base import EmbeddingProvider, NormalizedDocument, Parser
from app.sources.models import SourceItem
from app.storage.service import StorageService

# The catalog type of chunks.embedding looks like vector(384); the guard parses the dimension.
_VECTOR_TYPE_PATTERN = re.compile(r"^vector\((\d+)\)$")


@dataclass
class _ItemContext:
    """The item-derived pipeline inputs, held as plain values outside the session lifecycle.

    Loaded ORM rows expire at every commit, while these values must survive the whole
    choreography, including the rollbacks on the failure paths.
    """

    source_item_id: UUID
    project_id: UUID
    filename: str
    raw_object_key: str


def _claim_run(*, db: Session, ingestion_run_id: UUID) -> bool:
    """Claim the queued run, returning False for a duplicate or stale delivery."""

    claimed = claim_run(db=db, run_id=ingestion_run_id)
    db.commit()
    return claimed


def _mark_run_failed(*, db: Session, run_id: UUID, expected: RunStatus, error: str) -> None:
    """Move the run from ``expected`` to failed with the error text, then commit."""

    mark_failed(db=db, run_id=run_id, expected=expected, error=error)
    db.commit()


def _normalized_payload(*, document: NormalizedDocument) -> dict[str, object]:
    """Return the title-elements-metadata mapping that both the hash and the row store."""

    return {
        "title": document.title,
        "elements": [
            {"type": element.type, "text": element.text, "level": element.level}
            for element in document.elements
        ],
        "metadata": document.metadata,
    }


def canonical_document_json(*, document: NormalizedDocument) -> str:
    """Return the canonical JSON serialization used to fingerprint a normalized document.

    Only title, elements, and metadata enter the hash: ids and timestamps would make
    every hash unique and leave the unique(source_item_id, content_hash) guard dead.
    """

    return json.dumps(_normalized_payload(document=document), sort_keys=True, separators=(",", ":"))


def _content_hash(*, text: str) -> str:
    """Return the sha256 hex digest of one UTF-8 string."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_item_context(*, db: Session, source_item_id: UUID) -> _ItemContext | None:
    """Return the item-derived pipeline inputs, read straight off the item row."""

    item = db.get(SourceItem, source_item_id)
    if item is None:
        return None
    return _ItemContext(
        source_item_id=item.id,
        project_id=item.project_id,
        filename=item.filename,
        raw_object_key=item.raw_object_key,
    )


def _fetch_raw_bytes(
    *,
    db: Session,
    run_id: UUID,
    storage: StorageService,
    raw_object_key: str,
) -> bytes | None:
    """Fetch the run's own raw bytes from storage, recording failures on the run."""

    try:
        return storage.get_object(key=raw_object_key)
    except Exception as exc:
        _mark_run_failed(db=db, run_id=run_id, expected=RunStatus.FETCHING, error=str(exc))
        return None


def _begin_processing(*, db: Session, run_id: UUID) -> bool:
    """Move the claimed run to processing, committed so the parse spans no transaction."""

    transitioned = start_processing(db=db, run_id=run_id)
    db.commit()
    return transitioned


def _no_text_content_error(*, filename: str) -> str:
    """Return the failure message for a document with nothing to chunk or index."""

    return f"no text content to index in {filename!r}"


def _build_chunk_rows(
    *,
    context: _ItemContext,
    document_id: UUID,
    chunks: list[ChunkText],
) -> list[Chunk]:
    """Build the chunk rows for one document, positions from enumeration."""

    return [
        Chunk(
            id=uuid4(),
            project_id=context.project_id,
            document_id=document_id,
            position=position,
            text=chunk.text,
            heading_path=chunk.heading_path,
            chunk_type="text",
            chunk_metadata={"filename": context.filename},
            content_hash=_content_hash(text=chunk.text),
        )
        for position, chunk in enumerate(chunks)
    ]


def _mark_run_ready_against_existing(
    *,
    db: Session,
    run_id: UUID,
    source_item_id: UUID,
    content_hash: str,
) -> None:
    """End the run as a ready no-op pointing at the already-stored identical document."""

    existing_id: UUID | None = db.scalar(
        select(Document.id).where(
            Document.source_item_id == source_item_id,
            Document.content_hash == content_hash,
        )
    )
    if existing_id is None:
        # Unreachable in S3 (the conflict proves the row exists); recorded for completeness.
        _mark_run_failed(
            db=db,
            run_id=run_id,
            expected=RunStatus.PROCESSING,
            error="conflicting document disappeared before reconciliation",
        )
        return
    mark_ready(db=db, run_id=run_id, expected=RunStatus.PROCESSING, document_id=existing_id)
    db.commit()


def _commit_document_set(
    *,
    db: Session,
    run_id: UUID,
    context: _ItemContext,
    parsed: NormalizedDocument,
    document_hash: str,
    chunks: list[ChunkText],
) -> None:
    """Commit the document, its chunks, the outbox event, and the indexing transition atomically."""

    document = Document(
        id=uuid4(),
        source_item_id=context.source_item_id,
        project_id=context.project_id,
        content_hash=document_hash,
        raw_object_key=context.raw_object_key,
        normalized_content=_normalized_payload(document=parsed),
    )
    db.add(document)
    try:
        # The document flushes alone: the unit of work orders INSERTs by table name when
        # no relationship declares the FK order, and the unique(source_item_id,
        # content_hash) backstop can only fire on this insert.
        db.flush()
    except IntegrityError:
        # The identical version is already stored, so this run is a no-op that ends ready
        # on the existing document instead of a failed one.
        db.rollback()
        _mark_run_ready_against_existing(
            db=db, run_id=run_id, source_item_id=context.source_item_id, content_hash=document_hash
        )
        return
    except Exception as exc:
        db.rollback()
        _mark_run_failed(db=db, run_id=run_id, expected=RunStatus.PROCESSING, error=str(exc))
        return
    db.add_all(_build_chunk_rows(context=context, document_id=document.id, chunks=chunks))
    enqueue_document_ready_for_embedding(db=db, document_id=document.id, ingestion_run_id=run_id)
    try:
        # Flush the chunks and event, then transition the run with its document_id FK satisfied.
        db.flush()
        transitioned = mark_indexing(db=db, run_id=run_id, document_id=document.id)
        if not transitioned:
            # The run moved elsewhere mid-flight: a stale delivery lands nothing.
            db.rollback()
            return
        db.commit()
    except Exception as exc:
        # Chunk or event failures, including their own integrity errors, are failures.
        db.rollback()
        _mark_run_failed(db=db, run_id=run_id, expected=RunStatus.PROCESSING, error=str(exc))


def _parse_and_index(
    *,
    db: Session,
    run_id: UUID,
    context: _ItemContext,
    raw_bytes: bytes,
    parser: Parser,
    settings: Settings,
) -> None:
    """Parse the raw bytes, chunk them, and commit the document set in one transaction."""

    try:
        parsed = parser.parse(filename=context.filename, content=raw_bytes)
        if parsed.elements:
            chunks = chunk_elements(
                elements=parsed.elements,
                target_tokens=settings.chunk_target_tokens,
                max_tokens=settings.chunk_max_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            )
        else:
            # chunk_elements raises on an empty element list, so element-free parses skip it.
            chunks = []
        if not chunks:
            # A headings-only document never becomes a silent zero-chunk document.
            _mark_run_failed(
                db=db,
                run_id=run_id,
                expected=RunStatus.PROCESSING,
                error=_no_text_content_error(filename=context.filename),
            )
            return
        document_hash = _content_hash(text=canonical_document_json(document=parsed))
        _commit_document_set(
            db=db,
            run_id=run_id,
            context=context,
            parsed=parsed,
            document_hash=document_hash,
            chunks=chunks,
        )
    except Exception as exc:
        # After the claim, no error is ever re-raised: the run row is the outcome record.
        db.rollback()
        _mark_run_failed(db=db, run_id=run_id, expected=RunStatus.PROCESSING, error=str(exc))


def ingest_source_item(
    *,
    db: Session,
    source_item_id: UUID,
    ingestion_run_id: UUID,
    raw_object_key: str,
    content_hash: str,
    storage: StorageService,
    parser: Parser,
    settings: Settings,
) -> None:
    """Ingest one queued run's file version end to end, recording every outcome on the run row.

    The claim guard makes duplicate and stale deliveries no-ops, and after a successful
    claim no error is re-raised: the run row is the outcome record. ``content_hash``
    mirrors the event payload's file-version identity; the bytes are addressed by the
    payload's ``raw_object_key`` and the stored document hash is computed from the
    parsed content, so the payload hash carries no further duty in this task.
    """

    if not _claim_run(db=db, ingestion_run_id=ingestion_run_id):
        return
    context = _load_item_context(db=db, source_item_id=source_item_id)
    if context is None:
        # Unreachable once the claim succeeded (the run's FK guarantees the item exists).
        _mark_run_failed(
            db=db,
            run_id=ingestion_run_id,
            expected=RunStatus.FETCHING,
            error=f"source item {source_item_id} not found",
        )
        return
    # End the read transaction: no transaction may span the storage or parser calls.
    db.commit()
    raw_bytes = _fetch_raw_bytes(
        db=db, run_id=ingestion_run_id, storage=storage, raw_object_key=raw_object_key
    )
    if raw_bytes is None:
        return
    if not _begin_processing(db=db, run_id=ingestion_run_id):
        return
    _parse_and_index(
        db=db,
        run_id=ingestion_run_id,
        context=context,
        raw_bytes=raw_bytes,
        parser=parser,
        settings=settings,
    )


def _embed_batches(
    *,
    db: Session,
    chunk_ids: list[UUID],
    chunk_texts: list[str],
    embedding_provider: EmbeddingProvider,
    batch_size: int,
) -> None:
    """Embed and update every chunk in batch-size groups, committing once per batch."""

    for start in range(0, len(chunk_ids), batch_size):
        ids = chunk_ids[start : start + batch_size]
        texts = chunk_texts[start : start + batch_size]
        vectors = embedding_provider.embed_documents(texts=texts)
        for chunk_id, vector in zip(ids, vectors, strict=True):
            db.execute(update(Chunk).where(Chunk.id == chunk_id).values(embedding=vector))
        db.commit()


def _mark_run_ready(*, db: Session, run_id: UUID) -> None:
    """Move the run from indexing to ready with finished_at, then commit."""

    mark_ready(db=db, run_id=run_id, expected=RunStatus.INDEXING)
    db.commit()


def embed_document(
    *,
    db: Session,
    document_id: UUID,
    ingestion_run_id: UUID,
    embedding_provider: EmbeddingProvider,
    settings: Settings,
) -> None:
    """Embed one document's chunks in batches and move the run to ready.

    A missing document is an acked no-op. In-place vector updates plus the deterministic
    stub provider make re-delivery naturally idempotent, and every failure lands on the
    run row instead of being re-raised.
    """

    document = db.get(Document, document_id)
    if document is None:
        return
    rows = db.execute(
        select(Chunk.id, Chunk.text).where(Chunk.document_id == document_id).order_by(Chunk.position)
    ).all()
    # Close the read transaction: the provider call runs outside any transaction.
    db.commit()
    try:
        _embed_batches(
            db=db,
            chunk_ids=[row[0] for row in rows],
            chunk_texts=[row[1] for row in rows],
            embedding_provider=embedding_provider,
            batch_size=settings.embedding_batch_size,
        )
        _mark_run_ready(db=db, run_id=ingestion_run_id)
    except Exception as exc:
        db.rollback()
        _mark_run_failed(db=db, run_id=ingestion_run_id, expected=RunStatus.INDEXING, error=str(exc))


def query_embedding_dimension(*, db: Session) -> int | None:
    """Return the vector dimension of the chunks.embedding column, or None when absent.

    Reading the catalog type catches schema drift without loading any chunk rows, and
    None also covers a column that is not a fixed-dimension vector.
    """

    data_type = db.scalar(
        text(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "WHERE c.relname = 'chunks' AND a.attname = 'embedding' "
            "AND a.attnum > 0 AND NOT a.attisdropped"
        )
    )
    if data_type is None:
        return None
    match = _VECTOR_TYPE_PATTERN.match(str(data_type))
    return int(match.group(1)) if match is not None else None


def verify_embedding_dimension(*, expected_dimension: int, actual_dimension: int | None) -> None:
    """Raise when the stored column dimension disagrees with the provider's.

    Failing fast here replaces a cryptic psycopg insert failure deep in the embed path
    after chunks are already committed.
    """

    if actual_dimension != expected_dimension:
        raise RuntimeError(
            f"chunks.embedding is vector({actual_dimension}) but the selected provider "
            f"emits {expected_dimension}; changing the dimension requires an Alembic migration"
        )


def run_startup_checks(*, db: Session, embedding_provider: EmbeddingProvider) -> None:
    """Run the worker's startup checks: query the catalog and verify the dimension."""

    verify_embedding_dimension(
        expected_dimension=embedding_provider.dimension,
        actual_dimension=query_embedding_dimension(db=db),
    )
