"""Tests for the answer prompt rendering."""

from uuid import uuid4

from app.answers.prompt import SYSTEM_PROMPT, build_user_prompt
from app.retrieval.service import RetrievedChunk


def _chunk(*, text: str, heading_path: list[str], filename: str = "handbook.pdf") -> RetrievedChunk:
    """Build one chunk value with a fresh id; only the rendered fields matter."""

    return RetrievedChunk(
        id=uuid4(),
        document_id=uuid4(),
        source_item_id=uuid4(),
        filename=filename,
        position=0,
        heading_path=heading_path,
        chunk_type="text",
        text=text,
        score=1.0,
        document_content_hash="hash-1",
    )


def test_blocks_numbered_in_rank_order() -> None:
    """Check the prompt numbers blocks by rank and keeps both chunk texts."""

    chunks = [
        _chunk(text="first passage text", heading_path=[]),
        _chunk(text="second passage text", heading_path=[]),
    ]
    prompt = build_user_prompt(query="alpha", chunks=chunks)
    assert prompt.index("[1]") < prompt.index("[2]")
    assert "first passage text" in prompt
    assert "second passage text" in prompt


def test_block_headers_render_filename_and_heading() -> None:
    """Check a header renders the filename and the joined heading path."""

    chunk = _chunk(text="rotate the key", heading_path=["Keys", "Rotation"])
    prompt = build_user_prompt(query="alpha", chunks=[chunk])
    assert "[1] handbook.pdf - Keys > Rotation" in prompt.splitlines()


def test_empty_heading_path_renders_filename_only() -> None:
    """Check an empty heading path renders the filename with no dash suffix."""

    chunk = _chunk(text="rotate the key", heading_path=[])
    prompt = build_user_prompt(query="alpha", chunks=[chunk])
    assert "[1] handbook.pdf" in prompt.splitlines()
    assert "[1] handbook.pdf - " not in prompt


def test_question_included() -> None:
    """Check the prompt carries the question header line."""

    prompt = build_user_prompt(query="how do I rotate the garage key", chunks=[])
    assert "Question: how do I rotate the garage key" in prompt


def test_system_prompt_instructs_citations() -> None:
    """Check the system prompt demands inline citations, scope, and brevity."""

    assert "[1]" in SYSTEM_PROMPT
    assert "only" in SYSTEM_PROMPT
    assert "concise" in SYSTEM_PROMPT
