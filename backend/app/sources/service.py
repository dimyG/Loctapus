"""Business logic for the project upload source, its items, and the uploads listing."""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ingestion.models import Document
from app.ingestion.runs import latest_run_status, request_ingestion
from app.ingestion.status import RunStatus
from app.sources.models import Source, SourceItem
from app.storage.service import StorageService, build_raw_object_key

# Control characters (C0 and C1 plus DEL) must never survive into a stored filename.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f\x80-\x9f]")

# A stored filename is display data and part of the storage key, so its length is capped.
MAX_FILENAME_LENGTH = 255

# The only file extensions this slice's upload path accepts, with their content types.
SUPPORTED_UPLOAD_TYPES: Mapping[str, str] = MappingProxyType(
    {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)


def sanitize_filename(*, filename: str) -> str:
    r"""Return the safe basename of a client-supplied filename, raising ValueError when unusable.

    Only the last ``/`` or ``\\`` segment is kept, control characters are dropped, and
    dot-only names are rejected; an empty result or a name longer than 255 characters
    is rejected because the stored name is both display data and part of the storage key.
    """

    basename = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    basename = _CONTROL_CHARACTERS.sub("", basename)
    if basename in (".", "..") or not basename or len(basename) > MAX_FILENAME_LENGTH:
        raise ValueError(f"filename sanitizes to an empty or over-long basename: {filename!r}")
    return basename


def upload_content_type(*, filename: str) -> str | None:
    """Return the content type this slice stores for ``filename``, by its suffix, or None."""

    dot = filename.rfind(".")
    if dot < 0:
        return None
    return SUPPORTED_UPLOAD_TYPES.get(filename[dot:].lower())


class DuplicateUploadError(Exception):
    """Raised when a filename is already taken by an upload that cannot be retried."""


@dataclass(frozen=True)
class UploadListing:
    """One listed upload: the item identity plus its derived latest status."""

    id: UUID
    project_id: UUID
    filename: str
    status: RunStatus
    created_at: datetime


def _upload_item(*, db: Session, project_id: UUID, filename: str) -> SourceItem | None:
    """Return the project's upload item with this exact filename, if any."""

    return db.execute(
        select(SourceItem)
        .join(Source, Source.id == SourceItem.source_id)
        .where(Source.project_id == project_id, Source.type == "upload", SourceItem.external_id == filename)
    ).scalar_one_or_none()


def get_upload_item(*, db: Session, project_id: UUID, upload_id: UUID) -> SourceItem | None:
    """Return the project's upload item with this id, if any."""

    return db.execute(
        select(SourceItem)
        .join(Source, Source.id == SourceItem.source_id)
        .where(Source.project_id == project_id, Source.type == "upload", SourceItem.id == upload_id)
    ).scalar_one_or_none()


def _is_retryable(*, db: Session, item: SourceItem) -> bool:
    """Return whether the item's latest run failed with no document ever indexed."""

    status = db.scalar(
        select(latest_run_status(source_item_id=SourceItem.id)).where(SourceItem.id == item.id)
    )
    document_exists = db.scalar(select(Document.id).where(Document.source_item_id == item.id)) is not None
    return status == RunStatus.FAILED and not document_exists


def _upload_source_id(*, db: Session, project_id: UUID) -> UUID:
    """Return the project's one upload source id, creating the row when missing (R5)."""

    db.execute(
        insert(Source)
        .values(id=uuid4(), project_id=project_id, type="upload")
        .on_conflict_do_nothing(index_elements=[Source.project_id], index_where=Source.type == "upload")
    )
    source_id = db.scalar(select(Source.id).where(Source.project_id == project_id, Source.type == "upload"))
    if source_id is None:
        # Unreachable: the insert above guarantees the row exists.
        raise RuntimeError("the project's upload source vanished between insert and select")
    return source_id


def upload_file(
    *,
    db: Session,
    project_id: UUID,
    filename: str,
    content: bytes,
    storage: StorageService,
) -> UploadListing:
    """Store one uploaded file as the project's upload item, with its queued run and event.

    The stored and Garage content types come from the file's extension (R6), never from
    a client header. The read transaction ends before the storage PUT (no transaction
    spans it), then one write transaction covers source, item, run, and event. A
    same-name item is retried only when its latest run failed with no document indexed
    (R2); otherwise the upload is a duplicate and replacement stays S7's
    replace-only-after-success path.
    """

    content_type = upload_content_type(filename=filename)
    if content_type is None:
        raise ValueError(f"unsupported upload filename: {filename!r}")
    existing = _upload_item(db=db, project_id=project_id, filename=filename)
    if existing is not None and not _is_retryable(db=db, item=existing):
        raise DuplicateUploadError(filename)
    content_hash = hashlib.sha256(content).hexdigest()
    item_id = existing.id if existing is not None else uuid4()
    raw_object_key = build_raw_object_key(
        project_id=project_id, source_item_id=item_id, content_hash=content_hash, filename=filename
    )
    # End the read transaction: no transaction may span the storage PUT.
    db.commit()
    storage.put_object(key=raw_object_key, content=content, content_type=content_type)

    source_id = _upload_source_id(db=db, project_id=project_id)
    if existing is None:
        item = SourceItem(
            id=item_id,
            source_id=source_id,
            project_id=project_id,
            external_id=filename,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            content_hash=content_hash,
            raw_object_key=raw_object_key,
        )
        db.add(item)
        try:
            # The flush fires the filename-unique race backstop.
            db.flush()
        except IntegrityError:
            db.rollback()
            raise DuplicateUploadError(filename) from None
    else:
        item = db.execute(select(SourceItem).where(SourceItem.id == item_id).with_for_update()).scalar_one()
        if not _is_retryable(db=db, item=item):
            db.rollback()
            raise DuplicateUploadError(filename)
        item.content_hash = content_hash
        item.raw_object_key = raw_object_key
        item.size_bytes = len(content)
        item.content_type = content_type
    request_ingestion(db=db, source_item_id=item_id, raw_object_key=raw_object_key, content_hash=content_hash)
    db.commit()
    db.refresh(item)
    return UploadListing(
        id=item.id,
        project_id=item.project_id,
        filename=item.filename,
        status=RunStatus.QUEUED,
        created_at=item.created_at,
    )


def delete_upload(*, db: Session, project_id: UUID, upload_id: UUID, storage: StorageService) -> bool:
    """Delete one upload item with its pipeline rows and stored bytes, returning whether it existed.

    The database cascade removes the item's documents, chunks, and runs in the same
    transaction, and conversation citations settle to NULL by their own FK. The object
    delete runs first and outside any transaction, so a storage failure leaves every
    row untouched; S3's idempotent delete keeps an item whose bytes are already gone
    deletable. A queued or running ingestion survives as a no-op: the worker's guarded
    transitions treat the vanished run row as a stale delivery.
    """

    item = get_upload_item(db=db, project_id=project_id, upload_id=upload_id)
    if item is None:
        return False
    raw_object_key = item.raw_object_key
    # End the read transaction: no transaction may span the storage DELETE.
    db.commit()
    storage.delete_object(key=raw_object_key)
    db.delete(item)
    db.commit()
    return True


def list_uploads(*, db: Session, project_id: UUID) -> list[UploadListing]:
    """List a project's uploads newest first by item creation, deriving the latest status."""

    rows = db.execute(
        select(
            SourceItem,
            func.coalesce(latest_run_status(source_item_id=SourceItem.id), RunStatus.QUEUED).label("status"),
        )
        .join(Source, Source.id == SourceItem.source_id)
        .where(Source.project_id == project_id, Source.type == "upload")
        .order_by(SourceItem.created_at.desc(), SourceItem.id.desc())
    ).all()
    return [
        UploadListing(
            id=item.id,
            project_id=item.project_id,
            filename=item.filename,
            status=RunStatus(status),
            created_at=item.created_at,
        )
        for item, status in rows
    ]
