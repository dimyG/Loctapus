"""Tests for the pure RRF fusion and the greedy diversity walk."""

from uuid import UUID, uuid4

import pytest

from app.retrieval.pipeline import FusedCandidate, StageCandidate, fuse_rrf, select_final

RRF_K = 60


def _stage(*, document_id: UUID) -> StageCandidate:
    """Return one leg candidate with a fresh chunk id and an ignored raw score."""

    return StageCandidate(chunk_id=uuid4(), document_id=document_id, score=0.5)


def _fused(*, document_id: UUID) -> FusedCandidate:
    """Return one fused candidate row for the walk tests."""

    return FusedCandidate(chunk_id=uuid4(), document_id=document_id, score=1.0)


def test_fuse_sums_both_legs() -> None:
    """Check a chunk seen by both legs scores the sum of both rank contributions."""

    doc = uuid4()
    shared_chunk = uuid4()
    vector = [
        StageCandidate(chunk_id=shared_chunk, document_id=doc, score=9.9),
        StageCandidate(chunk_id=uuid4(), document_id=doc, score=8.8),
    ]
    fts = [
        StageCandidate(chunk_id=uuid4(), document_id=doc, score=0.1),
        StageCandidate(chunk_id=shared_chunk, document_id=doc, score=0.2),
    ]
    fused = fuse_rrf(vector=vector, fts=fts, rrf_k=RRF_K)
    shared_row = next(row for row in fused if row.chunk_id == shared_chunk)
    # Vector rank 1 plus fts rank 2, whatever the raw leg scores were.
    assert shared_row.score == pytest.approx(1 / 61 + 1 / 62)
    assert fused[0].chunk_id == shared_chunk


def test_fuse_uses_one_based_ranks() -> None:
    """Check a leg's first position contributes 1/(rrf_k+1), not 1/rrf_k."""

    chunk = _stage(document_id=uuid4())
    fused = fuse_rrf(vector=[chunk], fts=[], rrf_k=RRF_K)
    assert fused[0].chunk_id == chunk.chunk_id
    assert fused[0].score == pytest.approx(1 / (RRF_K + 1))


def test_fuse_orders_by_score_then_best_rank_then_id() -> None:
    """Check fused ties fall through to the ascending chunk id."""

    low = UUID(int=10)
    high = UUID(int=20)
    doc = uuid4()
    fused = fuse_rrf(
        vector=[StageCandidate(chunk_id=high, document_id=doc, score=0.0)],
        fts=[StageCandidate(chunk_id=low, document_id=doc, score=0.0)],
        rrf_k=RRF_K,
    )
    # Equal rank multisets tie on score and best rank, so the id decides.
    assert [row.chunk_id for row in fused] == [low, high]


def test_fuse_orders_equal_scores_by_best_rank() -> None:
    """Check equal fused scores fall back to the best single-leg rank before the id."""

    # Ranks (3, 24) and (12, 12) fuse to bit-identical 1/36, so only best_rank
    # separates the two chunks; the larger id must not win the tie.
    x_id = UUID(int=20)
    y_id = UUID(int=10)
    doc = uuid4()
    vector = [StageCandidate(chunk_id=uuid4(), document_id=doc, score=0.0) for _ in range(24)]
    fts = [StageCandidate(chunk_id=uuid4(), document_id=doc, score=0.0) for _ in range(24)]
    vector[2] = StageCandidate(chunk_id=x_id, document_id=doc, score=0.0)
    vector[11] = StageCandidate(chunk_id=y_id, document_id=doc, score=0.0)
    fts[11] = StageCandidate(chunk_id=y_id, document_id=doc, score=0.0)
    fts[23] = StageCandidate(chunk_id=x_id, document_id=doc, score=0.0)
    fused = fuse_rrf(vector=vector, fts=fts, rrf_k=RRF_K)
    assert fused[0].score == fused[1].score
    assert [row.chunk_id for row in fused[:2]] == [x_id, y_id]


def test_fuse_handles_empty_leg() -> None:
    """Check one empty leg still fuses the other leg's candidates in rank order."""

    first = _stage(document_id=uuid4())
    second = _stage(document_id=uuid4())
    fused = fuse_rrf(vector=[first, second], fts=[], rrf_k=RRF_K)
    assert [row.chunk_id for row in fused] == [first.chunk_id, second.chunk_id]


def test_select_final_preserves_fused_order_and_truncates() -> None:
    """Check the walk keeps fused order and stops at top_k."""

    rows = [_fused(document_id=uuid4()) for _ in range(3)]
    selected = select_final(fused=rows, top_k=2, max_chunks_per_document=None)
    assert selected == rows[:2]


def test_select_final_caps_per_document() -> None:
    """Check the walk skips past-cap documents and resumes uncapped ones."""

    doc_a = uuid4()
    doc_b = uuid4()
    rows = [
        _fused(document_id=doc_a),
        _fused(document_id=doc_b),
        _fused(document_id=doc_a),
        _fused(document_id=doc_b),
        _fused(document_id=doc_a),
    ]
    capped_once = select_final(fused=rows, top_k=3, max_chunks_per_document=1)
    # Both documents cap at one, so top_k=3 underfills rather than break the cap.
    assert capped_once == [rows[0], rows[1]]
    capped_twice = select_final(fused=rows, top_k=3, max_chunks_per_document=2)
    assert capped_twice == [rows[0], rows[1], rows[2]]


def test_select_final_null_cap_never_skips() -> None:
    """Check cap None keeps the fused top_k head under any document skew."""

    doc_a = uuid4()
    rows = [
        _fused(document_id=doc_a),
        _fused(document_id=uuid4()),
        _fused(document_id=doc_a),
        _fused(document_id=uuid4()),
    ]
    selected = select_final(fused=rows, top_k=3, max_chunks_per_document=None)
    assert selected == rows[:3]


def test_select_final_underfills_short_pool() -> None:
    """Check a pool smaller than top_k returns every candidate, not an error."""

    rows = [_fused(document_id=uuid4()), _fused(document_id=uuid4())]
    selected = select_final(fused=rows, top_k=10, max_chunks_per_document=1)
    assert selected == rows
