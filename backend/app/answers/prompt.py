"""Rendering of the system and user prompts for grounded answers.

Pure rendering over domain rows: this module never touches SQLAlchemy, so the
prompt contract can be tested without a database.
"""

from typing import Final

from app.retrieval.service import RetrievedChunk

SYSTEM_PROMPT: Final = (
    "Answer the user's question using only the supplied context passages. "
    "Cite the passage numbers you used inline, like [1] or [2]. "
    "If the context does not contain the answer, say so plainly. Be concise."
)


def _render_block(*, number: int, chunk: RetrievedChunk) -> str:
    """Render one numbered context block: its header line, then its text."""

    header = f"[{number}] {chunk.filename}"
    if chunk.heading_path:
        header += f" - {' > '.join(chunk.heading_path)}"
    return f"{header}\n{chunk.text}"


def build_user_prompt(*, query: str, chunks: list[RetrievedChunk]) -> str:
    """Render the question and the numbered context blocks in rank order."""

    blocks = [_render_block(number=n, chunk=chunk) for n, chunk in enumerate(chunks, start=1)]
    return "\n\n".join([f"Question: {query}", *blocks])
