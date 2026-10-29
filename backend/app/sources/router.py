"""Upload HTTP endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.projects.service import get_project_for_user_with_role, get_project_visible_to_user
from app.sources.schemas import UploadOut
from app.sources.service import (
    DuplicateUploadError,
    UploadListing,
    delete_upload,
    get_upload_item,
    list_uploads,
    sanitize_filename,
    upload_content_type,
    upload_file,
)
from app.storage.service import (
    ObjectNotFoundError,
    StorageService,
    StorageUnavailableError,
    get_storage,
)

router = APIRouter()


def _validated_filename(*, file: UploadFile) -> str:
    """Return the sanitized filename, raising 422 for an unusable name or extension."""

    try:
        filename = sanitize_filename(filename=file.filename or "")
    except ValueError:
        raise HTTPException(422, "The file name is not supported.") from None
    if upload_content_type(filename=filename) is None:
        raise HTTPException(422, "Only PDF and DOCX files are supported.")
    return filename


def _validated_size(*, file: UploadFile, settings: Settings) -> None:
    """Reject empty and oversized uploads via ``UploadFile.size`` before the bytes are read."""

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if file.size is None:
        # Defensive: Starlette always sets size on parsed multipart parts, so an absent
        # size means the body was never measured and cannot be gated.
        raise HTTPException(422, "The file size could not be determined.")
    if file.size == 0:
        raise HTTPException(422, "The file is empty.")
    if file.size > max_bytes:
        raise HTTPException(422, f"The file is too large. The maximum size is {settings.max_upload_mb} MB.")


def _to_out(*, listing: UploadListing) -> UploadOut:
    """Map one upload listing into its response body."""

    return UploadOut(
        id=listing.id,
        project_id=listing.project_id,
        filename=listing.filename,
        status=listing.status,
        created_at=listing.created_at,
    )


@router.post("/projects/{project_id}/uploads", status_code=201, response_model=UploadOut)
def upload(
    *,
    project_id: UUID,
    file: Annotated[UploadFile, File()],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    storage: StorageService = Depends(get_storage),
) -> UploadOut:
    """Store one uploaded file as the project's upload item, raising 404, 409, 422, or 503."""

    project = get_project_for_user_with_role(db=db, user=user, project_id=project_id, minimum_role="editor")
    if project is None:
        raise HTTPException(404, "project not found")
    filename = _validated_filename(file=file)
    _validated_size(file=file, settings=settings)
    content = file.file.read()
    try:
        listing = upload_file(
            db=db,
            project_id=project.id,
            filename=filename,
            content=content,
            storage=storage,
        )
    except DuplicateUploadError:
        raise HTTPException(409, "A file with this name already exists in this project.") from None
    except StorageUnavailableError:
        raise HTTPException(503, "Could not store the file. Please try again.") from None
    return _to_out(listing=listing)


@router.get("/projects/{project_id}/uploads", response_model=list[UploadOut])
def list_all(
    *,
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UploadOut]:
    """List a project's uploads newest first, raising 404 when the project is not visible."""

    project = get_project_visible_to_user(db=db, user=user, project_id=project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return [_to_out(listing=listing) for listing in list_uploads(db=db, project_id=project.id)]


@router.delete("/projects/{project_id}/uploads/{upload_id}", status_code=204)
def delete(
    *,
    project_id: UUID,
    upload_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage),
) -> None:
    """Delete one upload item with its pipeline rows and stored bytes, raising 404 or 503."""

    project = get_project_for_user_with_role(db=db, user=user, project_id=project_id, minimum_role="editor")
    if project is None:
        raise HTTPException(404, "project not found")
    try:
        deleted = delete_upload(db=db, project_id=project.id, upload_id=upload_id, storage=storage)
    except StorageUnavailableError:
        raise HTTPException(503, "Could not delete the file. Please try again.") from None
    if not deleted:
        raise HTTPException(404, "upload not found")


@router.get("/projects/{project_id}/uploads/{upload_id}/raw")
def download_raw(
    *,
    project_id: UUID,
    upload_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage),
) -> Response:
    """Return the upload's stored bytes, raising 404 or 503."""

    project = get_project_visible_to_user(db=db, user=user, project_id=project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    item = get_upload_item(db=db, project_id=project.id, upload_id=upload_id)
    if item is None:
        raise HTTPException(404, "upload not found")
    try:
        content = storage.get_object(key=item.raw_object_key)
    except ObjectNotFoundError:
        raise HTTPException(404, "file not found") from None
    except StorageUnavailableError:
        raise HTTPException(503, "Could not load the file. Please try again.") from None
    # Inline disposition lets a new browser tab render PDFs instead of forcing a download.
    return Response(
        content=content,
        media_type=item.content_type,
        headers={"Content-Disposition": f'inline; filename="{item.filename}"'},
    )
