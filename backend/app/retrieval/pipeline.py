"""Pure retrieval-stage math: reciprocal rank fusion and the diversity walk.

No SQLAlchemy, no settings, no providers here: the module stays importable and
testable without a database, and the service owns every query. Both legs hand
in rank-ordered lists - first element is rank 1 - and RRF consumes ranks only,
so the legs' raw scores (cosine distance, ts_rank) never meet each other.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class StageCandidate:
    """One leg's ranked result row: chunk identity plus the leg's raw score."""

    chunk_id: UUID
    document_id: UUID
    score: float


@dataclass(frozen=True)
class FusedCandidate:
    """One fused candidate: chunk identity plus the RRF score."""

    chunk_id: UUID
    document_id: UUID
    score: float


@dataclass
class _Fusion:
    """The running fusion state of one chunk across both legs."""

    document_id: UUID
    best_rank: int
    score: float


def fuse_rrf(*, vector: list[StageCandidate], fts: list[StageCandidate], rrf_k: int) -> list[FusedCandidate]:
    """Fuse both legs' rank-ordered candidates with reciprocal rank fusion.

    Each leg contributes ``1 / (rrf_k + rank)`` per chunk it returned; ties
    order by descending fused score, then the chunk's best single-leg rank,
    then the ascending chunk id, so the result is always deterministic.
    """

    states: dict[UUID, _Fusion] = {}
    for leg in (vector, fts):
        for rank, candidate in enumerate(leg, start=1):
            contribution = 1.0 / (rrf_k + rank)
            state = states.get(candidate.chunk_id)
            if state is None:
                states[candidate.chunk_id] = _Fusion(
                    document_id=candidate.document_id, best_rank=rank, score=contribution
                )
            else:
                state.score += contribution
                state.best_rank = min(state.best_rank, rank)

    ordered = sorted(states.items(), key=lambda item: (-item[1].score, item[1].best_rank, item[0]))
    return [
        FusedCandidate(chunk_id=chunk_id, document_id=state.document_id, score=state.score)
        for chunk_id, state in ordered
    ]


def select_final(
    *, fused: list[FusedCandidate], top_k: int, max_chunks_per_document: int | None
) -> list[FusedCandidate]:
    """Walk fused order, skipping past-cap documents, collecting ``top_k``.

    ``max_chunks_per_document=None`` never skips. The walk may underfill when
    every document reaches its cap before ``top_k`` - a short answer beats a
    repeated-document one.
    """

    per_document: dict[UUID, int] = {}
    selected: list[FusedCandidate] = []
    for candidate in fused:
        if len(selected) >= top_k:
            break
        taken = per_document.get(candidate.document_id, 0)
        if max_chunks_per_document is not None and taken >= max_chunks_per_document:
            continue
        per_document[candidate.document_id] = taken + 1
        selected.append(candidate)
    return selected
