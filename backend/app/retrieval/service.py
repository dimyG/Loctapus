"""The retrieval service: both search legs, fusion, selection, enrichment, logging.

The pipeline math stays pure in ``app.retrieval.pipeline``; this module owns every
SQL query and the per-query log row. ``latency_ms`` measures embed through selection,
excluding the log row's own insert.
"""

import math
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.ingestion.models import Chunk, Document
from app.providers import get_embedding_provider
from app.retrieval.models import QueryLog
from app.retrieval.pipeline import FusedCandidate, StageCandidate, fuse_rrf, select_final
from app.retrieval.schemas import RetrieveIn
from app.sources.models import SourceItem


@dataclass(frozen=True)
class RetrievedChunk:
    """One final result row: chunk fields, source filename, and fused score."""

    id: UUID
    document_id: UUID
    source_item_id: UUID
    filename: str
    position: int
    heading_path: list[str]
    chunk_type: str
    text: str
    score: float


def _search_vector_leg(
    *, db: Session, project_id: UUID, query_vector: list[float], limit: int
) -> list[StageCandidate]:
    """Return the project's indexed chunks nearest to the query vector by cosine.

    NaN distances come from zero-norm chunk embeddings: cosine distance is
    undefined there, so those rows drop instead of ranking or logging as NaN.
    """

    distance = Chunk.embedding.cosine_distance(query_vector)
    rows = (
        db.query(Chunk.id, Chunk.document_id, distance.label("score"))
        .filter(Chunk.project_id == project_id, Chunk.embedding.is_not(None))
        .order_by(distance, Chunk.id)
        .limit(limit)
        .all()
    )
    return [
        StageCandidate(chunk_id=id_, document_id=document_id, score=float(score))
        for id_, document_id, score in rows
        if not math.isnan(float(score))
    ]


def _search_fts_leg(*, db: Session, project_id: UUID, query: str, limit: int) -> list[StageCandidate]:
    """Return the project's indexed chunks ranked by ts_rank for the websearch query."""

    tsquery = func.websearch_to_tsquery("english", query)
    rank = func.ts_rank(Chunk.search_vector, tsquery)
    rows = (
        db.query(Chunk.id, Chunk.document_id, rank.label("score"))
        .filter(
            Chunk.project_id == project_id,
            Chunk.embedding.is_not(None),
            Chunk.search_vector.op("@@")(tsquery),
        )
        .order_by(rank.desc(), Chunk.id)
        .limit(limit)
        .all()
    )
    return [
        StageCandidate(chunk_id=id_, document_id=document_id, score=float(score))
        for id_, document_id, score in rows
    ]


def _enrich(*, db: Session, rows: list[FusedCandidate]) -> list[RetrievedChunk]:
    """Join the final chunks with their document's source item for serving fields."""

    final_ids = [row.chunk_id for row in rows]
    joined = (
        db.query(Chunk, Document.source_item_id, SourceItem.filename)
        .join(Document, Document.id == Chunk.document_id)
        .join(SourceItem, SourceItem.id == Document.source_item_id)
        .filter(Chunk.id.in_(final_ids))
        .all()
    )
    by_chunk = {chunk.id: (chunk, source_item_id, filename) for chunk, source_item_id, filename in joined}
    return [
        RetrievedChunk(
            id=row.chunk_id,
            document_id=row.document_id,
            source_item_id=by_chunk[row.chunk_id][1],
            filename=by_chunk[row.chunk_id][2],
            position=by_chunk[row.chunk_id][0].position,
            heading_path=by_chunk[row.chunk_id][0].heading_path,
            chunk_type=by_chunk[row.chunk_id][0].chunk_type,
            text=by_chunk[row.chunk_id][0].text,
            score=row.score,
        )
        for row in rows
    ]


def _log_query(
    *,
    db: Session,
    project_id: UUID,
    user_id: UUID,
    params: RetrieveIn,
    settings: Settings,
    origin: str,
    latency_ms: int,
    vector: list[StageCandidate],
    fts: list[StageCandidate],
    fused: list[FusedCandidate],
    final: list[FusedCandidate],
) -> None:
    """Write and commit one query log row: request echo, settings snapshot, stages."""

    log = QueryLog(
        project_id=project_id,
        user_id=user_id,
        query=params.query,
        params={
            "top_k": params.top_k,
            "rerank": params.rerank,
            "max_chunks_per_document": params.max_chunks_per_document,
            "origin": origin,
            "settings": {
                "rrf_k": settings.rrf_k,
                "candidates_per_retriever": settings.retrieval_candidates_per_retriever,
                "embedding_provider": settings.embedding_provider,
            },
        },
        latency_ms=latency_ms,
        stages={
            "vector": [
                {"chunk_id": str(candidate.chunk_id), "score": candidate.score} for candidate in vector
            ],
            "fts": [{"chunk_id": str(candidate.chunk_id), "score": candidate.score} for candidate in fts],
            "fused": [{"chunk_id": str(candidate.chunk_id), "score": candidate.score} for candidate in fused],
            "final": [str(candidate.chunk_id) for candidate in final],
        },
    )
    db.add(log)
    db.commit()


def _is_zero_vector(*, vector: list[float]) -> bool:
    """Return True when every component is zero, so cosine distance is undefined."""

    return not any(vector)


def retrieve(
    *,
    db: Session,
    project_id: UUID,
    user_id: UUID,
    params: RetrieveIn,
    settings: Settings,
    origin: str = "direct",
) -> list[RetrievedChunk]:
    """Embed, search both legs, fuse, select, enrich, and log one query.

    ``origin`` labels the caller surface in the log row. An all-stopword query
    degrades to the vector leg alone; a project with no indexed chunks returns
    an empty list and still writes its log row.
    """

    started = time.perf_counter()
    provider = get_embedding_provider(settings=settings)
    query_vector = provider.embed_query(text=params.query)
    candidates = settings.retrieval_candidates_per_retriever
    # A zero-norm query vector ranks nothing (every distance is NaN); fts still serves.
    vector = (
        []
        if _is_zero_vector(vector=query_vector)
        else _search_vector_leg(db=db, project_id=project_id, query_vector=query_vector, limit=candidates)
    )
    fts = _search_fts_leg(db=db, project_id=project_id, query=params.query, limit=candidates)
    fused = fuse_rrf(vector=vector, fts=fts, rrf_k=settings.rrf_k)
    final = select_final(
        fused=fused, top_k=params.top_k, max_chunks_per_document=params.max_chunks_per_document
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    chunks = _enrich(db=db, rows=final)
    _log_query(
        db=db,
        project_id=project_id,
        user_id=user_id,
        params=params,
        settings=settings,
        origin=origin,
        latency_ms=latency_ms,
        vector=vector,
        fts=fts,
        fused=fused,
        final=final,
    )
    return chunks
