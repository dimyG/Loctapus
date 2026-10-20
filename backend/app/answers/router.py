"""Grounded-answer HTTP endpoint."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.answers.schemas import AnswerIn, AnswerOut
from app.answers.service import generate_answer
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.projects.service import get_project_visible_to_user
from app.providers import LLMError
from app.retrieval.schemas import RetrievedChunkOut
from app.retrieval.service import RetrievedChunk

_logger = logging.getLogger(__name__)

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


@router.post("/projects/{project_id}/answer", response_model=AnswerOut)
def answer_question(
    *,
    project_id: UUID,
    body: AnswerIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AnswerOut:
    """Generate one grounded answer for one query, raising 401, 404, 422, or 502."""

    project = get_project_visible_to_user(db=db, user=user, project_id=project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    try:
        answer = generate_answer(
            db=db, project_id=project.id, user_id=user.id, params=body, settings=settings
        )
    except LLMError as error:
        _logger.warning("Answer generation failed", exc_info=error)
        raise HTTPException(502, str(error)) from error
    return AnswerOut(answer=answer.text, chunks=[_to_out(chunk=chunk) for chunk in answer.chunks])
