"""The answer service: route each turn, answer along its path, persist the conversation."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy.orm import Session

from app.answers.prompt import (
    ROUTER_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_DIRECT,
    ContextBlock,
    build_answer_messages,
    build_route_messages,
)
from app.answers.schemas import AnswerIn
from app.conversations.models import ConversationMessageChunk
from app.conversations.service import (
    SnapshotIn,
    append_turn,
    gather_snapshots,
    load_history,
    resolve_conversation,
)
from app.core.config import Settings
from app.providers import RouteDecision, get_llm_provider
from app.providers.base import ChatMessage, LLMError
from app.retrieval.schemas import RetrieveIn
from app.retrieval.service import RetrievedChunk, retrieve

CANNED_EMPTY_ANSWER: Final = "No indexed content in this project matches your question yet."


@dataclass(frozen=True)
class Answer:
    """One generated answer plus the exact rows that grounded it."""

    text: str
    route: str
    conversation_id: UUID
    chunks: Sequence[RetrievedChunk | ConversationMessageChunk]


def _resolve_retrieve_in(*, query: str, params: AnswerIn, settings: Settings) -> RetrieveIn:
    """Fill the request's omitted retrieval overrides from the answer settings."""

    return RetrieveIn(
        query=query,
        top_k=settings.answer_context_chunks if params.top_k is None else params.top_k,
        rerank=params.rerank,
        max_chunks_per_document=(
            settings.answer_max_chunks_per_document
            if params.max_chunks_per_document is None
            else params.max_chunks_per_document
        ),
    )


def _effective_question(*, raw: str, decision: RouteDecision) -> str:
    """Return the standalone search question: the rewrite, or the raw question."""

    if decision.route == "retrieve" and decision.rewritten_query:
        return decision.rewritten_query
    return raw


def _context_blocks(*, chunks: Sequence[RetrievedChunk | ConversationMessageChunk]) -> list[ContextBlock]:
    """Render fresh or stored evidence rows as prompt context blocks."""

    return [
        ContextBlock(filename=chunk.filename, heading_path=chunk.heading_path, text=chunk.text)
        for chunk in chunks
    ]


def _snapshot_from(*, chunk: RetrievedChunk | ConversationMessageChunk) -> SnapshotIn:
    """Map one fresh or stored evidence row into its persisted snapshot shape."""

    chunk_id = chunk.id if isinstance(chunk, RetrievedChunk) else chunk.chunk_id
    return SnapshotIn(
        chunk_id=chunk_id,
        filename=chunk.filename,
        heading_path=chunk.heading_path,
        text=chunk.text,
        document_content_hash=chunk.document_content_hash,
    )


def generate_answer(
    *, db: Session, project_id: UUID, user_id: UUID, params: AnswerIn, settings: Settings
) -> Answer | None:
    """Route one turn, answer along its path, and persist the whole turn.

    Returns ``None`` only when an explicit ``conversation_id`` is not the
    caller's; the router maps that to a 404.
    """

    conversation = resolve_conversation(
        db=db, project_id=project_id, user_id=user_id, conversation_id=params.conversation_id
    )
    if conversation is None:
        return None
    # A pending row (null path, first turn) has no id yet: its history and REUSE set are empty.
    history: list[ChatMessage] = []
    gathered: list[ConversationMessageChunk] = []
    if conversation.id is not None:
        history = load_history(db=db, conversation_id=conversation.id, limit=settings.answer_history_messages)
        gathered = gather_snapshots(
            db=db, conversation_id=conversation.id, max_chunks=settings.answer_reuse_max_chunks
        )

    provider = get_llm_provider(settings=settings)
    router_fallback = False
    try:
        decision = provider.route(
            system=ROUTER_SYSTEM_PROMPT,
            messages=build_route_messages(
                question=params.query, history=history, evidence=_context_blocks(chunks=gathered)
            ),
        )
    except LLMError:
        # A failed router call degrades to retrieval with the raw question (decision 6).
        decision = RouteDecision(route="retrieve", rewritten_query=None)
        router_fallback = True

    route = decision.route
    if route == "reuse" and not gathered:
        # Nothing was ever cited in this conversation: only fresh retrieval can ground.
        route = "retrieve"

    answer_chunks: Sequence[RetrievedChunk | ConversationMessageChunk]
    if route == "direct":
        text = provider.generate(
            system=SYSTEM_PROMPT_DIRECT,
            messages=[*history, ChatMessage(role="user", content=params.query)],
        )
        answer_chunks = []
    elif route == "reuse":
        text = provider.generate(
            system=SYSTEM_PROMPT,
            messages=build_answer_messages(
                question=params.query, history=history, blocks=_context_blocks(chunks=gathered)
            ),
        )
        answer_chunks = list(gathered)
    else:
        fresh = retrieve(
            db=db,
            project_id=project_id,
            user_id=user_id,
            params=_resolve_retrieve_in(
                query=_effective_question(raw=params.query, decision=decision),
                params=params,
                settings=settings,
            ),
            settings=settings,
            origin="answer",
            log_context={
                "route": route,
                "raw_query": params.query,
                **({"router_fallback": "true"} if router_fallback else {}),
            },
        )
        if not fresh:
            # An empty index answers from the can; the LLM never sees a context-less question.
            append_turn(
                db=db,
                conversation=conversation,
                question=params.query,
                answer=CANNED_EMPTY_ANSWER,
                route=route,
                snapshots=[],
            )
            return Answer(
                text=CANNED_EMPTY_ANSWER,
                route=route,
                conversation_id=conversation.id,
                chunks=[],
            )
        text = provider.generate(
            system=SYSTEM_PROMPT,
            messages=build_answer_messages(
                question=params.query, history=history, blocks=_context_blocks(chunks=fresh)
            ),
        )
        answer_chunks = fresh

    append_turn(
        db=db,
        conversation=conversation,
        question=params.query,
        answer=text,
        route=route,
        snapshots=[_snapshot_from(chunk=chunk) for chunk in answer_chunks],
    )
    return Answer(
        text=text,
        route=route,
        conversation_id=conversation.id,
        chunks=answer_chunks,
    )
