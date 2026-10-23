"""Rendering of the system and user prompts for grounded answers and turn routing.

Pure rendering over domain rows: this module never touches SQLAlchemy, so the
prompt contract can be tested without a database.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from app.providers.base import ChatMessage
from app.retrieval.service import RetrievedChunk

SYSTEM_PROMPT: Final = (
    "Answer the user's question using only the supplied context passages. "
    "Cite the passage numbers you used inline, like [1] or [2]. "
    "If the context does not contain the answer, say so plainly. Be concise."
)

ROUTER_SYSTEM_PROMPT: Final = (
    "You route one follow-up question in a document chat. Reply with ONLY one JSON object "
    'on a single line: {"route": "direct" | "reuse" | "retrieve", "rewritten_query": "..."} . '
    '"direct": the conversation history alone answers the question, so no passages are needed. '
    '"reuse": the question resolves against the EVIDENCE SUMMARY excerpts from earlier turns. '
    '"retrieve": fresh retrieval is needed, and "rewritten_query" carries the standalone search '
    "question with no pronouns pointing back into the history. "
    '"rewritten_query" is required on "retrieve" and may be null otherwise. '
    "Prefer retrieve when unsure."
)

SYSTEM_PROMPT_DIRECT: Final = (
    "Answer the user's question from the supplied conversation history alone. "
    "No context passages are supplied. "
    "If the history does not contain the answer, say so plainly. Be concise."
)

# Each evidence excerpt in the router prompt previews at most this many characters,
# so the routing call stays small while the answer call still cites the full text.
EVIDENCE_PREVIEW_CHARS: Final = 200


@dataclass(frozen=True)
class ContextBlock:
    """One renderable context passage: fresh chunks and stored snapshots map into it."""

    filename: str
    heading_path: list[str]
    text: str


def _render_block(*, number: int, block: ContextBlock) -> str:
    """Render one numbered context block: its header line, then its text."""

    header = f"[{number}] {block.filename}"
    if block.heading_path:
        header += f" - {' > '.join(block.heading_path)}"
    return f"{header}\n{block.text}"


def _render_evidence(*, blocks: Sequence[ContextBlock]) -> str:
    """Render the evidence summary message for the router prompt."""

    rows = [
        _render_block(number=number, block=_previewed(block=block))
        for number, block in enumerate(blocks, start=1)
    ]
    return "\n".join(["EVIDENCE SUMMARY (excerpts cited in earlier turns):", *rows])


def _previewed(*, block: ContextBlock) -> ContextBlock:
    """Return one block with its text cut to the preview length."""

    return ContextBlock(
        filename=block.filename,
        heading_path=block.heading_path,
        text=block.text[:EVIDENCE_PREVIEW_CHARS],
    )


def build_user_prompt(*, query: str, chunks: list[RetrievedChunk]) -> str:
    """Render the question and the numbered context blocks in rank order."""

    blocks = [
        ContextBlock(filename=chunk.filename, heading_path=chunk.heading_path, text=chunk.text)
        for chunk in chunks
    ]
    rendered = [_render_block(number=number, block=block) for number, block in enumerate(blocks, start=1)]
    return "\n\n".join([f"Question: {query}", *rendered])


def build_route_messages(
    *, question: str, history: list[ChatMessage], evidence: Sequence[ContextBlock]
) -> list[ChatMessage]:
    """Render the router messages: history, the evidence summary, then the question.

    The evidence set is the same gathered set a REUSE answer reuses, so the
    router's judgment is honest.
    """

    messages = list(history)
    if evidence:
        messages.append(ChatMessage(role="user", content=_render_evidence(blocks=evidence)))
    messages.append(ChatMessage(role="user", content=question))
    return messages


def build_answer_messages(
    *, question: str, history: list[ChatMessage], blocks: Sequence[ContextBlock]
) -> list[ChatMessage]:
    """Render the answer messages: history, then the final grounded question."""

    messages = list(history)
    rendered = [_render_block(number=number, block=block) for number, block in enumerate(blocks, start=1)]
    messages.append(
        ChatMessage(
            role="user",
            content="\n\n".join([f"Question: {question}", *rendered]),
        )
    )
    return messages
