"""The answer service: resolve the retrieval defaults, then prompt and generate."""

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy.orm import Session

from app.answers.prompt import SYSTEM_PROMPT, build_user_prompt
from app.answers.schemas import AnswerIn
from app.core.config import Settings
from app.providers import get_llm_provider
from app.retrieval.schemas import RetrieveIn
from app.retrieval.service import RetrievedChunk, retrieve

CANNED_EMPTY_ANSWER: Final = "No indexed content in this project matches your question yet."


@dataclass(frozen=True)
class Answer:
    """One generated answer plus the retrieval rows that grounded it."""

    text: str
    chunks: list[RetrievedChunk]


def _resolve_retrieve_in(*, params: AnswerIn, settings: Settings) -> RetrieveIn:
    """Fill the request's omitted retrieval overrides from the answer settings."""

    return RetrieveIn(
        query=params.query,
        top_k=settings.answer_context_chunks if params.top_k is None else params.top_k,
        rerank=params.rerank,
        max_chunks_per_document=(
            settings.answer_max_chunks_per_document
            if params.max_chunks_per_document is None
            else params.max_chunks_per_document
        ),
    )


def generate_answer(
    *, db: Session, project_id: UUID, user_id: UUID, params: AnswerIn, settings: Settings
) -> Answer:
    """Resolve the retrieval defaults, retrieve, prompt, and generate one answer."""

    # The answer round labels its log row so chat history can be told from direct calls.
    chunks = retrieve(
        db=db,
        project_id=project_id,
        user_id=user_id,
        params=_resolve_retrieve_in(params=params, settings=settings),
        settings=settings,
        origin="answer",
    )
    # An empty index answers from the can; the LLM never sees a context-less question.
    if not chunks:
        return Answer(text=CANNED_EMPTY_ANSWER, chunks=[])
    provider = get_llm_provider(settings=settings)
    return Answer(
        text=provider.generate(
            system=SYSTEM_PROMPT, user=build_user_prompt(query=params.query, chunks=chunks)
        ),
        chunks=chunks,
    )
