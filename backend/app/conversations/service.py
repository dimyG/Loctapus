"""The conversations service: ownership resolution, persistence, and history reads."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.conversations.models import Conversation, ConversationMessage, ConversationMessageChunk
from app.providers.base import ChatMessage

# History rides the prompts without its citation markers: only the fresh context
# blocks carry [n] numbers, so old turns cannot renumber the live answer.
_CITATION_MARKERS: re.Pattern[str] = re.compile(r"\s*\[\d+\]")


@dataclass(frozen=True)
class SnapshotIn:
    """One evidence snapshot an assistant message persists beside its answer."""

    chunk_id: UUID | None
    filename: str
    heading_path: list[str]
    text: str
    document_content_hash: str


def create_conversation(*, db: Session, project_id: UUID, user_id: UUID) -> Conversation:
    """Create and commit one empty conversation owned by the caller."""

    conversation = Conversation(project_id=project_id, user_id=user_id)
    db.add(conversation)
    db.commit()
    return conversation


def get_latest_conversation(*, db: Session, project_id: UUID, user_id: UUID) -> Conversation | None:
    """Return the owner's most recent conversation in one project, if any."""

    latest = db.scalars(
        select(Conversation)
        .where(Conversation.project_id == project_id, Conversation.user_id == user_id)
        .order_by(Conversation.last_message_at.desc())
        .limit(1)
    ).first()
    # Read-only close: no transaction stays open across the LLM calls that follow.
    db.commit()
    return latest


def resolve_conversation(
    *, db: Session, project_id: UUID, user_id: UUID, conversation_id: UUID | None
) -> Conversation | None:
    """Resolve one turn's conversation, or ``None`` when an explicit id is not the owner's.

    On the null path with no prior row, the returned conversation is pending (no id):
    it joins the append transaction instead of persisting here.
    """

    # conversation_id arrives null only before hydration resolves: first entry into a
    # project's chat, or a submit racing the GET-latest fetch. Null always means
    # latest-or-create, never create-new, so the race resolves to the existing row.
    if conversation_id is None:
        latest = get_latest_conversation(db=db, project_id=project_id, user_id=user_id)
        if latest is not None:
            return latest
        return Conversation(project_id=project_id, user_id=user_id)
    return db.scalars(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.project_id == project_id,
            Conversation.user_id == user_id,
        )
    ).first()


def load_history(*, db: Session, conversation_id: UUID, limit: int) -> list[ChatMessage]:
    """Return the conversation's last ``limit`` messages oldest-first, citations stripped."""

    rows = db.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.position.desc())
        .limit(limit)
    ).all()
    history = [
        ChatMessage(
            role=cast(Literal["user", "assistant"], row.role),
            content=_CITATION_MARKERS.sub("", row.content),
        )
        for row in reversed(rows)
    ]
    # Read-only close: no transaction stays open across the LLM calls that follow.
    db.commit()
    return history


def gather_snapshots(
    *, db: Session, conversation_id: UUID, max_chunks: int
) -> list[ConversationMessageChunk]:
    """Return the conversation's newest evidence snapshots, deduped and capped.

    Walk the assistant messages newest-first and keep each chunk's first sighting;
    a snapshot whose chunk row is gone (``chunk_id`` null) dedupes on its durable
    text and filename instead. The rows keep their stored ordinals: the caller
    cites them positionally.
    """

    rows = db.scalars(
        select(ConversationMessageChunk)
        .join(ConversationMessage, ConversationMessage.id == ConversationMessageChunk.message_id)
        .where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.role == "assistant",
        )
        .order_by(ConversationMessage.position.desc(), ConversationMessageChunk.ordinal)
    ).all()
    seen: set[UUID | tuple[str, str]] = set()
    gathered: list[ConversationMessageChunk] = []
    for row in rows:
        key = row.chunk_id if row.chunk_id is not None else (row.text, row.filename)
        if key in seen:
            continue
        seen.add(key)
        gathered.append(row)
        if len(gathered) == max_chunks:
            break
    # Read-only close: no transaction stays open across the LLM calls that follow.
    db.commit()
    return gathered


def list_messages(
    *, db: Session, conversation_id: UUID
) -> list[tuple[ConversationMessage, list[ConversationMessageChunk]]]:
    """Return the conversation's messages oldest-first with their snapshot chunks."""

    messages = db.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.position)
    ).all()
    snapshots: list[ConversationMessageChunk] = (
        list(
            db.scalars(
                select(ConversationMessageChunk)
                .where(ConversationMessageChunk.message_id.in_([message.id for message in messages]))
                .order_by(ConversationMessageChunk.message_id, ConversationMessageChunk.ordinal)
            )
        )
        if messages
        else []
    )
    by_message: dict[UUID, list[ConversationMessageChunk]] = {}
    for snapshot in snapshots:
        by_message.setdefault(snapshot.message_id, []).append(snapshot)
    # Read-only close: the response is fully materialized, so the request leaves
    # no open transaction behind.
    db.commit()
    return [(message, by_message.get(message.id, [])) for message in messages]


def append_turn(
    *,
    db: Session,
    conversation: Conversation,
    question: str,
    answer: str,
    route: str,
    snapshots: Sequence[SnapshotIn],
) -> None:
    """Append one user/assistant turn in a single transaction, bumping last_message_at.

    The row lock on the conversation serializes concurrent turns so positions
    never collide.
    """

    # The conversation row joins this transaction on the null path: a failed answer call
    # must persist nothing, not even an empty conversation (spec decision 14).
    db.add(conversation)
    db.flush()
    db.execute(select(Conversation.id).where(Conversation.id == conversation.id).with_for_update())
    next_position = 1 + (
        db.scalar(
            select(func.max(ConversationMessage.position)).where(
                ConversationMessage.conversation_id == conversation.id
            )
        )
        or 0
    )
    db.add(
        ConversationMessage(
            conversation_id=conversation.id,
            position=next_position,
            role="user",
            content=question,
        )
    )
    assistant = ConversationMessage(
        conversation_id=conversation.id,
        position=next_position + 1,
        role="assistant",
        content=answer,
        route=route,
    )
    db.add(assistant)
    db.flush()
    db.add_all(
        [
            ConversationMessageChunk(
                message_id=assistant.id,
                ordinal=ordinal,
                chunk_id=snapshot.chunk_id,
                filename=snapshot.filename,
                heading_path=snapshot.heading_path,
                text=snapshot.text,
                document_content_hash=snapshot.document_content_hash,
            )
            for ordinal, snapshot in enumerate(snapshots, start=1)
        ]
    )
    conversation.last_message_at = datetime.now(UTC)
    db.commit()
