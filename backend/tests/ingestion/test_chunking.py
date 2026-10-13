"""Golden tests for the structure-aware chunker."""

import math

import pytest

from app.ingestion.chunking import ChunkText, chunk_elements
from app.providers.base import NormalizedElement

TARGET_TOKENS = 20
MAX_TOKENS = 40
OVERLAP_TOKENS = 8


def _paragraph(*, word_count: int, tag: str) -> str:
    """Build a text with exactly ``word_count`` unique, countable words."""

    return " ".join(f"{tag}-{index}" for index in range(word_count))


def _paragraph_element(*, word_count: int, tag: str) -> NormalizedElement:
    """Build a paragraph element carrying exactly ``word_count`` words."""

    return NormalizedElement(type="paragraph", text=_paragraph(word_count=word_count, tag=tag))


def _heading(*, text: str, level: int | None) -> NormalizedElement:
    """Build a heading element with an optional level."""

    return NormalizedElement(type="heading", text=text, level=level)


def _estimate_tokens(*, text: str) -> int:
    """Re-derive the documented estimate, ceil(words * 4 / 3), independently."""

    return math.ceil(len(text.split()) * 4 / 3)


def _chunk(*, elements: list[NormalizedElement]) -> list[ChunkText]:
    """Chunk ``elements`` with the standard golden-test budgets."""

    return chunk_elements(
        elements=elements,
        target_tokens=TARGET_TOKENS,
        max_tokens=MAX_TOKENS,
        overlap_tokens=OVERLAP_TOKENS,
    )


def _heading_boundary_elements() -> list[NormalizedElement]:
    """Three 5-word paragraphs split by a second heading into two packs."""

    return [
        _heading(text="Alpha", level=1),
        _paragraph_element(word_count=5, tag="a"),
        _paragraph_element(word_count=5, tag="b"),
        _heading(text="Beta", level=1),
        _paragraph_element(word_count=5, tag="c"),
    ]


def _packing_elements() -> list[NormalizedElement]:
    """Paragraphs sized so the third would push the pack over the 20-token target."""

    return [
        _heading(text="Alpha", level=1),
        _paragraph_element(word_count=5, tag="a"),
        _paragraph_element(word_count=10, tag="b"),
        _paragraph_element(word_count=10, tag="c"),
    ]


def _oversize_elements() -> list[NormalizedElement]:
    """Build a single 60-word paragraph whose estimate exceeds the 40-token max."""

    return [_paragraph_element(word_count=60, tag="big")]


def _stack_elements() -> list[NormalizedElement]:
    """Build a level-1 heading, a level-2 heading, and a heading with no level."""

    return [
        _heading(text="Alpha", level=1),
        _paragraph_element(word_count=5, tag="a"),
        _heading(text="Beta", level=2),
        _paragraph_element(word_count=5, tag="b"),
        _heading(text="Omega", level=None),
        _paragraph_element(word_count=5, tag="o"),
    ]


def _tiny_elements() -> list[NormalizedElement]:
    """One short paragraph and no headings."""

    return [_paragraph_element(word_count=5, tag="only")]


def _headings_only_elements() -> list[NormalizedElement]:
    """Two headings and no paragraph text at all."""

    return [_heading(text="Alpha", level=1), _heading(text="Beta", level=2)]


def _edge_budget_elements() -> list[NormalizedElement]:
    """Build a paragraph exactly on the max boundary and one word over it."""

    return [_paragraph_element(word_count=30, tag="onmax"), _paragraph_element(word_count=31, tag="over")]


def _all_fixtures() -> list[list[NormalizedElement]]:
    """Return every fixture document, for invariants that must hold everywhere."""

    return [
        _heading_boundary_elements(),
        _packing_elements(),
        _oversize_elements(),
        _stack_elements(),
        _tiny_elements(),
        _headings_only_elements(),
        _edge_budget_elements(),
    ]


def test_heading_boundaries_start_new_chunks() -> None:
    """Check that a pack never spans a heading."""

    chunks = _chunk(elements=_heading_boundary_elements())
    assert len(chunks) == 2
    assert chunks[0].heading_path == ["Alpha"]
    assert chunks[0].text == f"{_paragraph(word_count=5, tag='a')}\n\n{_paragraph(word_count=5, tag='b')}"
    assert chunks[1].heading_path == ["Beta"]
    assert chunks[1].text == _paragraph(word_count=5, tag="c")


def test_packing_stops_at_target() -> None:
    """Check that the overflowing element starts the next chunk instead of enlarging the current one."""

    chunks = _chunk(elements=_packing_elements())
    assert len(chunks) == 2
    assert chunks[0].text == f"{_paragraph(word_count=5, tag='a')}\n\n{_paragraph(word_count=10, tag='b')}"
    assert _estimate_tokens(text=chunks[0].text) == TARGET_TOKENS
    assert chunks[1].text == _paragraph(word_count=10, tag="c")


def test_oversize_element_hard_splits_with_overlap() -> None:
    """Check that one over-max element splits into under-max windows sharing overlap-sized prefixes."""

    chunks = _chunk(elements=_oversize_elements())
    words = _paragraph(word_count=60, tag="big").split()
    # floor(40 * 3 / 4) = 30 words per window, stepping back the 8-word overlap.
    assert [chunk.text for chunk in chunks] == [
        " ".join(words[0:30]),
        " ".join(words[22:52]),
        " ".join(words[44:60]),
    ]
    for first, second in zip(chunks, chunks[1:], strict=False):
        assert second.text.split()[:OVERLAP_TOKENS] == first.text.split()[-OVERLAP_TOKENS:]


def test_heading_path_records_the_stack() -> None:
    """Check that level-1 then level-2 headings give ["h1"] then ["h1", "h2"]."""

    chunks = _chunk(elements=_stack_elements())
    assert [chunk.heading_path for chunk in chunks] == [["Alpha"], ["Alpha", "Beta"], ["Omega"]]


def test_tiny_document_yields_one_chunk() -> None:
    """Check that one short paragraph yields exactly one chunk with an empty path."""

    chunks = _chunk(elements=_tiny_elements())
    assert len(chunks) == 1
    assert chunks[0].text == _paragraph(word_count=5, tag="only")
    assert chunks[0].heading_path == []


def test_headings_only_document_yields_zero_chunks() -> None:
    """Check that a headings-only document yields zero chunks."""

    assert _chunk(elements=_headings_only_elements()) == []


def test_empty_element_list_raises() -> None:
    """Check that an empty element list raises ValueError."""

    with pytest.raises(ValueError, match="empty"):
        _chunk(elements=[])


def test_heading_text_not_duplicated_into_chunk_text() -> None:
    """Check that heading text is recorded only in heading_path."""

    elements = [_heading(text="Alpha", level=1), _paragraph_element(word_count=5, tag="only")]
    chunks = _chunk(elements=elements)
    assert [chunk.text for chunk in chunks] == [_paragraph(word_count=5, tag="only")]


def test_no_chunk_exceeds_max_tokens() -> None:
    """Re-assert the max-token invariant across every fixture's chunked output."""

    for elements in _all_fixtures():
        for chunk in _chunk(elements=elements):
            assert _estimate_tokens(text=chunk.text) <= MAX_TOKENS, chunk.text
