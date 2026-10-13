"""Structure-aware chunking of normalized document elements."""

from dataclasses import dataclass, field
from math import ceil, floor

from app.providers.base import NormalizedElement


@dataclass
class ChunkText:
    """One emitted chunk: its text and the heading path leading to it."""

    text: str
    heading_path: list[str]


def _estimate_tokens(*, words: int) -> int:
    """Estimate the token count of ``words`` words as ``ceil(words * 4 / 3)``.

    The 4/3 ratio is a documented English-prose average; the estimate avoids a
    tokenizer dependency so chunk budgets stay stable across deployments.
    """

    return ceil(words * 4 / 3)


def _hard_split(*, text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Split one over-max text into word windows that each stay at or under max.

    Windows hold ``floor(max_tokens * 3 / 4)`` words, the largest word count
    whose estimate cannot exceed ``max_tokens``, and step back by
    ``overlap_tokens`` words so consecutive windows share that many-word prefix.
    """

    words = text.split()
    window_words = floor(max_tokens * 3 / 4)
    stride = window_words - overlap_tokens
    if stride < 1:
        raise ValueError("overlap_tokens must leave at least one new word per hard-split window")
    windows: list[str] = []
    start = 0
    while start < len(words):
        windows.append(" ".join(words[start : start + window_words]))
        # The final window may be short; a further step would only repeat overlap.
        if start + window_words >= len(words):
            break
        start += stride
    return windows


@dataclass
class _PendingPack:
    """Accumulator for the paragraphs that will form the next emitted chunk."""

    texts: list[str] = field(default_factory=list)
    words: int = 0

    def would_exceed_target(self, *, words: int, target_tokens: int) -> bool:
        """Report whether adding ``words`` more words would push the pack over target."""

        return _estimate_tokens(words=self.words + words) > target_tokens

    def add(self, *, text: str) -> None:
        """Append one paragraph text and its word count to the pack."""

        self.texts.append(text)
        self.words += len(text.split())

    def flush(self, *, chunks: list[ChunkText], stack: list[str]) -> None:
        """Emit the accumulated paragraphs as one chunk under ``stack``, then reset."""

        if self.texts:
            chunks.append(ChunkText(text="\n\n".join(self.texts), heading_path=list(stack)))
        self.texts = []
        self.words = 0


def _advance_stack(*, stack: list[str], element: NormalizedElement) -> list[str]:
    """Return the heading stack after ``element``, with a missing level treated as 1."""

    level = element.level if element.level is not None else 1
    return stack[: level - 1] + [element.text]


def _absorb_paragraph(
    *,
    element: NormalizedElement,
    pack: _PendingPack,
    chunks: list[ChunkText],
    stack: list[str],
    target_tokens: int,
    max_tokens: int,
    overlap_tokens: int,
) -> None:
    """Fold one paragraph element into the pack, hard-splitting it when it is oversized."""

    words = len(element.text.split())
    if _estimate_tokens(words=words) > max_tokens:
        # An element over max never enlarges the current pack; its windows are chunks.
        pack.flush(chunks=chunks, stack=stack)
        for window in _hard_split(text=element.text, max_tokens=max_tokens, overlap_tokens=overlap_tokens):
            chunks.append(ChunkText(text=window, heading_path=list(stack)))
        return
    if pack.texts and pack.would_exceed_target(words=words, target_tokens=target_tokens):
        # Packing stops at the target, so the overflowing element starts the next chunk.
        pack.flush(chunks=chunks, stack=stack)
    pack.add(text=element.text)


def chunk_elements(
    *,
    elements: list[NormalizedElement],
    target_tokens: int,
    max_tokens: int,
    overlap_tokens: int,
) -> list[ChunkText]:
    """Chunk normalized elements into retrieval-sized pieces.

    Consecutive paragraphs pack under one heading path until adding the next
    would exceed ``target_tokens``; a single element over ``max_tokens``
    hard-splits by words into windows that overlap by ``overlap_tokens`` words.
    No emitted chunk's estimate exceeds ``max_tokens``. Headings are recorded
    only in ``heading_path``. Raises ``ValueError`` on an empty element list,
    or when ``overlap_tokens`` leaves no new word for a hard-split window, and
    returns ``[]`` for a headings-only document. The max-token invariant
    presumes ``target_tokens <= max_tokens``.
    """

    if not elements:
        raise ValueError("elements must not be empty")
    chunks: list[ChunkText] = []
    stack: list[str] = []
    pack = _PendingPack()
    for element in elements:
        if element.type == "heading":
            # Flush before advancing so the pack keeps the path it was built under.
            pack.flush(chunks=chunks, stack=stack)
            stack = _advance_stack(stack=stack, element=element)
        else:
            _absorb_paragraph(
                element=element,
                pack=pack,
                chunks=chunks,
                stack=stack,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
            )
    pack.flush(chunks=chunks, stack=stack)
    return chunks
