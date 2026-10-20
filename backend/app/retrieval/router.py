"""Retrieval HTTP endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.projects.service import get_project_visible_to_user
from app.retrieval.schemas import RetrievedChunkOut, RetrieveIn
from app.retrieval.service import RetrievedChunk, retrieve

router = APIRouter()


def _to_out(*, chunk: RetrievedChunk) -> RetrievedChunkOut:
    """Map one retrieved chunk into its response body."""

    return RetrievedChunkOut(
        id=chunk.id,
        document_id=chunk.document_id,
        source_item_id=chunk.source_item_id,
        filename=chunk.filename,
        position=chunk.position,
        heading_path=chunk.heading_path,
        chunk_type=chunk.chunk_type,
        text=chunk.text,
        score=chunk.score,
    )


@router.post("/projects/{project_id}/retrieve", response_model=list[RetrievedChunkOut])
def retrieve_chunks(
    *,
    project_id: UUID,
    body: RetrieveIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[RetrievedChunkOut]:
    """Return fused, diversity-selected grounded chunks for one query."""

    project = get_project_visible_to_user(db=db, user=user, project_id=project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    chunks = retrieve(db=db, project_id=project.id, user_id=user.id, params=body, settings=settings)
    return [_to_out(chunk=chunk) for chunk in chunks]
