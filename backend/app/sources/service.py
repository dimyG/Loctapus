"""Business logic for upload sources, their items, and the derived source listing."""

import hashlib
import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.ingestion.runs import latest_run_status, request_ingestion
from app.ingestion.status import RunStatus
from app.projects.models import Project
from app.sources.models import Source, SourceItem
from app.storage.service import StorageService, build_raw_object_key

# Control characters (C0 plus DEL) must never survive into a stored filename.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")

# A stored filename is display data and part of the storage key, so its length is capped.
MAX_FILENAME_LENGTH = 255


def sanitize_filename(*, filename: str) -> str:
    r"""Return the safe basename of a client-supplied filename, raising ValueError when unusable.

    Only the last ``/`` or ``\\`` segment is kept and control characters are dropped; an
    empty result or a name longer than 255 characters is rejected because the stored name
    is both display data and part of the storage key.
    """

    basename = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    basename = _CONTROL_CHARACTERS.sub("", basename)
    if not basename or len(basename) > MAX_FILENAME_LENGTH:
        raise ValueError(f"filename sanitizes to an empty or over-long basename: {filename!r}")
    return basename


def create_upload_source(
    *,
    db: Session,
    project: Project,
    filename: str,
    content_type: str | None,
    content: bytes,
    storage: StorageService,
    settings: Settings,
) -> Source:
    """Store one uploaded file and commit its source, item, queued run, and outbox event.

    The request's read transaction is committed before the storage PUT so that no DB
    transaction spans the storage call, and the rows land in one later transaction:
    raw bytes persist first, then the relational state, atomically. ``settings`` is
    accepted for signature symmetry with the worker services; the upload size gate
    lives in the router's pre-read validation.
    """

    content_hash = hashlib.sha256(content).hexdigest()
    source_id = uuid4()
    item_id = uuid4()
    raw_object_key = build_raw_object_key(
        project_id=project.id,
        source_item_id=item_id,
        content_hash=content_hash,
        filename=filename,
    )
    # Copy the ids the rest of the flow still needs, then end the read transaction with a
    # commit: a rollback would discard the test harness savepoint's setup rows, and any
    # instance access after a rollback would silently reopen a transaction across the PUT.
    project_id = project.id
    db.commit()
    storage.put_object(key=raw_object_key, content=content, content_type=content_type)

    # One transaction for source, item, run, and event, flushed in FK order because the
    # unit of work would otherwise order these unrelated mappers by table name.
    source = Source(id=source_id, project_id=project_id, type="upload")
    db.add(source)
    db.flush()
    item = SourceItem(
        id=item_id,
        source_id=source_id,
        project_id=project_id,
        external_id=filename,
        filename=filename,
        content_type=content_type or "application/octet-stream",
        size_bytes=len(content),
        content_hash=content_hash,
        raw_object_key=raw_object_key,
    )
    db.add(item)
    db.flush()
    request_ingestion(db=db, source_item_id=item_id, raw_object_key=raw_object_key, content_hash=content_hash)
    db.commit()
    return source


@dataclass
class SourceListItem:
    """One listed source with its derived display fields."""

    source: Source
    filename: str
    status: str


def list_sources(*, db: Session, project_id: UUID) -> list[SourceListItem]:
    """List a project's sources newest first, deriving filename and status from the latest run.

    The latest run is the correlated lookup with the id tie-break, so a tied
    ``created_at`` cannot fan one item out into several rows; an item with no visible
    run coalesces to queued (defensive).
    """

    rows = db.execute(
        select(
            Source,
            SourceItem,
            func.coalesce(latest_run_status(source_item_id=SourceItem.id), RunStatus.QUEUED).label("status"),
        )
        .join(SourceItem, SourceItem.source_id == Source.id)
        .where(Source.project_id == project_id)
        .order_by(Source.created_at.desc(), Source.id.desc())
    ).all()
    return [
        SourceListItem(source=source, filename=item.filename, status=status) for source, item, status in rows
    ]
