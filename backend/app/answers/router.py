"""Grounded-answer HTTP endpoint."""

import logging
from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.answers.schemas import AnswerIn, AnswerOut
from app.answers.service import Answer, generate_answer
from app.conversations.models import ConversationMessageChunk
from app.conversations.schemas import SnapshotChunkOut
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.projects.service import get_project_visible_to_user
from app.providers import LLMError
from app.retrieval.service import RetrievedChunk

_logger = logging.getLogger(__name__)

router = APIRouter()


def _to_out(*, chunk: RetrievedChunk | ConversationMessageChunk) -> SnapshotChunkOut:
    """Map one fresh or stored evidence row into its response body."""

    chunk_id = chunk.id if isinstance(chunk, RetrievedChunk) else chunk.chunk_id
    return SnapshotChunkOut(
        chunk_id=chunk_id,
        filename=chunk.filename,
        heading_path=chunk.heading_path,
        text=chunk.text,
        document_content_hash=chunk.document_content_hash,
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
    if answer is None:
        # An explicit conversation id the caller does not own.
        raise HTTPException(404, "conversation not found")
    return _to_answer_out(answer=answer)


def _to_answer_out(*, answer: Answer) -> AnswerOut:
    """Map one service answer into its response body."""

    return AnswerOut(
        answer=answer.text,
        # The service stores the route as text; the column check pins the literals.
        route=cast(Literal["direct", "reuse", "retrieve"], answer.route),
        conversation_id=answer.conversation_id,
        chunks=[_to_out(chunk=chunk) for chunk in answer.chunks],
    )
