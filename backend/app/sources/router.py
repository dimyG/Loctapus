"""Source HTTP endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.ingestion.status import RunStatus
from app.projects.service import get_project_for_user_with_role, get_project_visible_to_user
from app.sources.schemas import SourceOut
from app.sources.service import create_upload_source, list_sources, sanitize_filename
from app.storage.service import StorageService, StorageUnavailableError

router = APIRouter()

# The only file extensions this slice's upload path accepts.
ALLOWED_EXTENSIONS = (".pdf", ".docx")


def _validated_filename(*, file: UploadFile) -> str:
    """Return the sanitized filename, raising 422 for an unusable name or extension."""

    try:
        filename = sanitize_filename(filename=file.filename or "")
    except ValueError:
        raise HTTPException(422, "The file name is not supported.") from None
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(422, "Only PDF and DOCX files are supported.")
    return filename


def _validated_size(*, file: UploadFile, settings: Settings) -> None:
    """Reject empty and oversized uploads via ``UploadFile.size`` before the bytes are read."""

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if file.size is None or file.size == 0:
        raise HTTPException(422, "The file is empty.")
    if file.size > max_bytes:
        raise HTTPException(422, f"The file is too large. The maximum size is {settings.max_upload_mb} MB.")


@router.post("/projects/{project_id}/sources", status_code=201, response_model=SourceOut)
def upload(
    *,
    project_id: UUID,
    file: Annotated[UploadFile, File()],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SourceOut:
    """Store an uploaded file as a new source, raising 404, 422, or 503 per the flow order."""

    project = get_project_for_user_with_role(db=db, user=user, project_id=project_id, minimum_role="editor")
    if project is None:
        raise HTTPException(404, "project not found")
    filename = _validated_filename(file=file)
    _validated_size(file=file, settings=settings)
    content = file.file.read()
    try:
        source = create_upload_source(
            db=db,
            project=project,
            filename=filename,
            content_type=file.content_type,
            content=content,
            storage=StorageService(settings=settings),
            settings=settings,
        )
    except StorageUnavailableError:
        raise HTTPException(503, "Could not store the file. Please try again.") from None
    # A source fresh from create_upload_source has exactly one run and it is queued.
    return SourceOut(
        id=source.id,
        project_id=source.project_id,
        type=source.type,
        status=RunStatus.QUEUED,
        filename=filename,
        created_at=source.created_at,
    )


@router.get("/projects/{project_id}/sources", response_model=list[SourceOut])
def list_all(
    *,
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SourceOut]:
    """List a project's sources newest first, raising 404 when the project is not visible."""

    project = get_project_visible_to_user(db=db, user=user, project_id=project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return [
        SourceOut(
            id=item.source.id,
            project_id=item.source.project_id,
            type=item.source.type,
            status=RunStatus(item.status),
            filename=item.filename,
            created_at=item.source.created_at,
        )
        for item in list_sources(db=db, project_id=project_id)
    ]
