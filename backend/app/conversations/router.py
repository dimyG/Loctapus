"""Conversations HTTP endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.conversations.schemas import (
    ConversationCreatedOut,
    LatestConversationOut,
    MessageOut,
    SnapshotChunkOut,
)
from app.conversations.service import create_conversation, get_latest_conversation, list_messages
from app.core.db import get_db
from app.identity.dependencies import get_current_user
from app.identity.models import User
from app.projects.service import get_project_visible_to_user

router = APIRouter()


@router.post("/projects/{project_id}/conversations", status_code=201, response_model=ConversationCreatedOut)
def start_conversation(
    *,
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationCreatedOut:
    """Create one empty conversation owned by the caller, raising 401 or 404."""

    project = get_project_visible_to_user(db=db, user=user, project_id=project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    conversation = create_conversation(db=db, project_id=project.id, user_id=user.id)
    return ConversationCreatedOut(conversation_id=conversation.id)


@router.get("/projects/{project_id}/conversations/latest", response_model=LatestConversationOut)
def latest_conversation(
    *,
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LatestConversationOut:
    """Return the caller's latest conversation with its full message history."""

    project = get_project_visible_to_user(db=db, user=user, project_id=project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    conversation = get_latest_conversation(db=db, project_id=project.id, user_id=user.id)
    if conversation is None:
        raise HTTPException(404, "no conversation yet")
    return LatestConversationOut(
        conversation_id=conversation.id,
        messages=[
            MessageOut(
                role=message.role,
                content=message.content,
                route=message.route,
                chunks=[
                    SnapshotChunkOut(
                        chunk_id=snapshot.chunk_id,
                        filename=snapshot.filename,
                        heading_path=snapshot.heading_path,
                        text=snapshot.text,
                        document_content_hash=snapshot.document_content_hash,
                    )
                    for snapshot in snapshots
                ],
            )
            for message, snapshots in list_messages(db=db, conversation_id=conversation.id)
        ],
    )
