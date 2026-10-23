"""Tests for the answer prompt rendering."""

from uuid import uuid4

from app.answers.prompt import (
    ROUTER_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_DIRECT,
    ContextBlock,
    build_answer_messages,
    build_route_messages,
    build_user_prompt,
)
from app.providers.base import ChatMessage
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


def _block(*, text: str, heading_path: list[str] | None = None, filename: str = "doc.pdf") -> ContextBlock:
    """Build one context block; only the rendered fields matter."""

    return ContextBlock(filename=filename, heading_path=heading_path or [], text=text)


def test_router_system_prompt_states_contract() -> None:
    """Check the router prompt names the routes, the JSON key, and strict JSON."""

    for word in ("direct", "reuse", "retrieve", "rewritten_query"):
        assert word in ROUTER_SYSTEM_PROMPT
    assert "JSON" in ROUTER_SYSTEM_PROMPT
    assert "unsure" in ROUTER_SYSTEM_PROMPT


def test_direct_system_prompt_has_no_passages() -> None:
    """Check the direct prompt answers from history without context passages."""

    assert "history" in SYSTEM_PROMPT_DIRECT
    assert "passages" in SYSTEM_PROMPT_DIRECT
    assert "concise" in SYSTEM_PROMPT_DIRECT


def test_route_messages_contain_history_evidence_and_question() -> None:
    """Check route messages order history, then the evidence summary, then the question."""

    history = [
        ChatMessage(role="user", content="what is alpha?"),
        ChatMessage(role="assistant", content="alpha is a letter"),
    ]
    evidence = [_block(text="x" * 250), _block(text="short", heading_path=["Intro", "Details"])]
    messages = build_route_messages(question="and what about beta?", history=history, evidence=evidence)
    assert messages[:2] == history
    summary = messages[2]
    assert summary.role == "user"
    assert "[1] doc.pdf" in summary.content
    assert "[2] doc.pdf - Intro > Details" in summary.content
    # Each excerpt previews at most the first 200 characters.
    assert "x" * 200 in summary.content
    assert "x" * 201 not in summary.content
    assert messages[3] == ChatMessage(role="user", content="and what about beta?")


def test_answer_messages_history_then_question_blocks() -> None:
    """Check answer messages keep history ahead of the final grounded question."""

    history = [ChatMessage(role="user", content="what is alpha?")]
    blocks = [_block(text="first"), _block(text="second", heading_path=["H"])]
    messages = build_answer_messages(question="more?", history=history, blocks=blocks)
    assert messages[0] == history[0]
    final = messages[1]
    assert final.role == "user"
    assert final.content.startswith("Question: more?")
    assert final.content.index("[1] doc.pdf\nfirst") < final.content.index("[2] doc.pdf - H\nsecond")


def test_history_passes_through_verbatim() -> None:
    """Check history arrives unmodified: load_history already stripped its markers."""

    history = [ChatMessage(role="assistant", content="clean answer")]
    messages = build_answer_messages(question="q", history=history, blocks=[])
    assert messages[0].content == "clean answer"
    assert messages[1].content == "Question: q"
