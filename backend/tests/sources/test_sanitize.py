"""Unit tests for filename sanitization."""

import pytest

from app.sources.service import sanitize_filename


def test_sanitize_keeps_a_plain_name() -> None:
    """Check that a plain filename passes through unchanged."""

    assert sanitize_filename(filename="notes.pdf") == "notes.pdf"


def test_sanitize_takes_the_last_forward_slash_segment() -> None:
    """Check that traversal segments are stripped from forward-slash paths."""

    assert sanitize_filename(filename="../evil/report.pdf") == "report.pdf"


def test_sanitize_takes_the_last_backslash_segment() -> None:
    """Check that backslash-separated segments are stripped too."""

    assert sanitize_filename(filename="dir\\x.pdf") == "x.pdf"


def test_sanitize_drops_control_characters() -> None:
    """Check that control characters never survive into the stored name."""

    assert sanitize_filename(filename="no\x00te\x1f.pdf") == "note.pdf"


def test_sanitize_rejects_names_over_255_characters() -> None:
    """Check that an over-long basename is rejected."""

    with pytest.raises(ValueError):
        sanitize_filename(filename="a" * 256 + ".pdf")


def test_sanitize_rejects_an_empty_basename() -> None:
    """Check that a name with no usable basename is rejected."""

    with pytest.raises(ValueError):
        sanitize_filename(filename="/")
