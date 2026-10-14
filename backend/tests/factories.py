"""Row factories shared across the S3 test modules.

``seed_project`` and ``seed_upload`` write the pipeline's baseline rows directly,
with no storage calls, so tests that do not need Garage bytes pay nothing for them.
"""

import hashlib
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.identity.service import register_user
from app.ingestion.models import IngestionRun
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
    orders INSERTs of unrelated mappers by table name.
    """

    source = Source(project_id=project_id, type="upload")
    db.add(source)
    db.flush()
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
        source_id=source.id,
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
    run = IngestionRun(id=uuid4(), source_item_id=item_id, status="queued")
    db.add(run)
    db.commit()
    return SeededUpload(
        source_id=source.id,
        source_item_id=item_id,
        ingestion_run_id=run.id,
        raw_object_key=raw_object_key,
        content_hash=content_hash,
    )
