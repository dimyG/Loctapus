"""Tests for the retrieval service, against the real Postgres."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.identity.models import User
from app.ingestion.models import Document
from app.providers.stub_embeddings import StubEmbeddingProvider
from app.retrieval.models import RetrieveLog
from app.retrieval.schemas import RetrieveIn
from app.retrieval.service import RetrievedChunk, _search_fts_leg, _search_vector_leg, retrieve
from tests.factories import seed_document_with_chunks, seed_project


def _seed_user(*, db: Session) -> User:
    """Seed one bare user row so the query log's foreign key resolves."""

    user = User(email=f"{uuid4()}@example.com", password_hash="x")
    db.add(user)
    db.flush()
    return user


def test_vector_leg_orders_by_cosine_distance(*, db_session: Session) -> None:
    """Check the vector leg returns chunks by ascending cosine distance."""

    project_id = seed_project(db=db_session, email="vector@example.com")
    seeded = seed_document_with_chunks(
        db=db_session,
        project_id=project_id,
        chunk_texts=["alpha alpha bravo", "alpha", "charlie"],
    )
    query_vector = StubEmbeddingProvider().embed_query(text="alpha bravo")
    rows = _search_vector_leg(db=db_session, project_id=project_id, query_vector=query_vector, limit=50)
    assert [row.chunk_id for row in rows] == seeded.chunk_ids


def test_fts_leg_orders_by_ts_rank(*, db_session: Session) -> None:
    """Check the fts leg ranks a repeated lexeme above a single one."""

    project_id = seed_project(db=db_session, email="fts@example.com")
    seeded = seed_document_with_chunks(
        db=db_session,
        project_id=project_id,
        chunk_texts=["quick quick quick", "quick brown"],
    )
    rows = _search_fts_leg(db=db_session, project_id=project_id, query="quick", limit=50)
    # Default ts_rank weighs lexeme frequency, not document length or coverage.
    assert [row.chunk_id for row in rows] == [seeded.chunk_ids[0], seeded.chunk_ids[1]]
    assert rows[0].score > rows[1].score
    assert rows[0].score > 0


def test_fts_leg_excludes_null_embeddings(*, db_session: Session) -> None:
    """Check a document still being embedded surfaces through neither leg."""

    project_id = seed_project(db=db_session, email="null-embed@example.com")
    seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["quick fox"], embed=False)
    fts = _search_fts_leg(db=db_session, project_id=project_id, query="quick fox", limit=50)
    vector = _search_vector_leg(
        db=db_session,
        project_id=project_id,
        query_vector=StubEmbeddingProvider().embed_query(text="quick fox"),
        limit=50,
    )
    assert fts == []
    assert vector == []


def test_stopword_only_query_uses_vector_leg_only(*, db_session: Session, settings: Settings) -> None:
    """Check an all-stopword query degrades to the vector leg and still answers."""

    project_id = seed_project(db=db_session, email="stopword@example.com")
    seeded = seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["the the"])
    user = _seed_user(db=db_session)
    result = retrieve(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=RetrieveIn(query="the"),
        settings=settings,
    )
    assert [chunk.id for chunk in result] == seeded.chunk_ids
    log = db_session.scalars(select(RetrieveLog).where(RetrieveLog.project_id == project_id)).one()
    assert log.stages["fts"] == []


def test_malformed_websearch_syntax_is_tolerated(*, db_session: Session, settings: Settings) -> None:
    """Check stray quotes and operators parse instead of raising."""

    project_id = seed_project(db=db_session, email="malformed@example.com")
    seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["alpha"])
    user = _seed_user(db=db_session)
    result = retrieve(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=RetrieveIn(query='alpha " or OR'),
        settings=settings,
    )
    assert isinstance(result, list)


def test_legs_are_scoped_to_the_project(*, db_session: Session, settings: Settings) -> None:
    """Check another project's chunks never surface in either leg."""

    project_a = seed_project(db=db_session, email="scope-a@example.com")
    project_b = seed_project(db=db_session, email="scope-b@example.com")
    seed_document_with_chunks(db=db_session, project_id=project_b, chunk_texts=["alpha"])
    user = _seed_user(db=db_session)
    fts = _search_fts_leg(db=db_session, project_id=project_a, query="alpha", limit=50)
    vector = _search_vector_leg(
        db=db_session,
        project_id=project_a,
        query_vector=StubEmbeddingProvider().embed_query(text="alpha"),
        limit=50,
    )
    result = retrieve(
        db=db_session,
        project_id=project_a,
        user_id=user.id,
        params=RetrieveIn(query="alpha"),
        settings=settings,
    )
    assert fts == []
    assert vector == []
    assert result == []


def test_retrieve_applies_max_chunks_per_document(*, db_session: Session, settings: Settings) -> None:
    """Check the walk skips same-document chunks past the cap and resumes others."""

    project_id = seed_project(db=db_session, email="cap@example.com")
    doc_a = seed_document_with_chunks(
        db=db_session,
        project_id=project_id,
        chunk_texts=["alpha", "alpha alpha", "alpha alpha alpha"],
        filename="a.pdf",
    )
    doc_b = seed_document_with_chunks(
        db=db_session, project_id=project_id, chunk_texts=["alpha bravo"], filename="b.pdf"
    )
    user = _seed_user(db=db_session)
    result = retrieve(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=RetrieveIn(query="alpha", top_k=2, max_chunks_per_document=1),
        settings=settings,
    )
    assert [chunk.document_id for chunk in result] == [doc_a.document_id, doc_b.document_id]


def test_retrieve_writes_one_query_log_row(*, db_session: Session, settings: Settings) -> None:
    """Check one retrieve writes exactly one log row echoing the request and stages."""

    project_id = seed_project(db=db_session, email="log@example.com")
    seed_document_with_chunks(
        db=db_session, project_id=project_id, chunk_texts=["alpha alpha", "alpha bravo"]
    )
    user = _seed_user(db=db_session)
    result = retrieve(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=RetrieveIn(query="  alpha  "),
        settings=settings,
    )
    logs = db_session.scalars(select(RetrieveLog).where(RetrieveLog.project_id == project_id)).all()
    assert len(logs) == 1
    log = logs[0]
    assert log.query == "alpha"
    assert log.user_id == user.id
    assert log.params["top_k"] == 10
    assert log.params["rerank"] is False
    assert log.params["max_chunks_per_document"] is None
    assert log.params["settings"]["rrf_k"] == 60
    assert log.params["settings"]["candidates_per_retriever"] == 50
    assert log.params["settings"]["embedding_provider"] == "stub"
    assert set(log.stages) == {"vector", "fts", "fused", "final"}
    # The stages keep their leg orderings: ascending cosine distance, descending rank.
    vector_scores = [entry["score"] for entry in log.stages["vector"]]
    assert vector_scores == sorted(vector_scores)
    fts_scores = [entry["score"] for entry in log.stages["fts"]]
    assert fts_scores == sorted(fts_scores, reverse=True)
    fused_scores = [entry["score"] for entry in log.stages["fused"]]
    assert fused_scores == sorted(fused_scores, reverse=True)
    # The walk is a prefix of the fused order, so the final ids are its head.
    fused_ids = [entry["chunk_id"] for entry in log.stages["fused"]]
    assert log.stages["final"] == fused_ids[:10]
    assert log.stages["final"] == [str(chunk.id) for chunk in result]
    assert log.latency_ms >= 0


def test_retrieve_logs_origin_direct_by_default(*, db_session: Session, settings: Settings) -> None:
    """Check a plain retrieve records the default origin in the log row."""

    project_id = seed_project(db=db_session, email="origin-default@example.com")
    seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["alpha"])
    user = _seed_user(db=db_session)
    retrieve(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=RetrieveIn(query="alpha"),
        settings=settings,
    )
    log = db_session.scalars(select(RetrieveLog).where(RetrieveLog.project_id == project_id)).one()
    assert log.params["origin"] == "direct"
    # A direct call passes no answer-layer context, so none leaks into params.
    assert "route" not in log.params
    assert "raw_query" not in log.params
    assert "router_fallback" not in log.params


def test_log_context_merges_into_params(*, db_session: Session, settings: Settings) -> None:
    """Check the answer round's routing context rides the log row's params."""

    project_id = seed_project(db=db_session, email="log-context@example.com")
    seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["alpha"])
    user = _seed_user(db=db_session)
    retrieve(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=RetrieveIn(query="alpha"),
        settings=settings,
        origin="answer",
        log_context={"route": "retrieve", "raw_query": "alpha?", "router_fallback": "true"},
    )
    log = db_session.scalars(select(RetrieveLog).where(RetrieveLog.project_id == project_id)).one()
    assert log.params["origin"] == "answer"
    assert log.params["route"] == "retrieve"
    assert log.params["raw_query"] == "alpha?"
    assert log.params["router_fallback"] == "true"


def test_retrieved_chunk_carries_document_hash(*, db_session: Session, settings: Settings) -> None:
    """Check the final rows carry their document's content hash for citations."""

    project_id = seed_project(db=db_session, email="doc-hash@example.com")
    seeded = seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["alpha alpha"])
    user = _seed_user(db=db_session)
    result = retrieve(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=RetrieveIn(query="alpha"),
        settings=settings,
    )
    document = db_session.get_one(Document, seeded.document_id)
    assert result[0].document_content_hash == document.content_hash


def test_retrieve_records_explicit_origin(*, db_session: Session, settings: Settings) -> None:
    """Check an explicit origin passes through to the log row."""

    project_id = seed_project(db=db_session, email="origin-answer@example.com")
    seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["alpha"])
    user = _seed_user(db=db_session)
    retrieve(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=RetrieveIn(query="alpha"),
        settings=settings,
        origin="answer",
    )
    log = db_session.scalars(select(RetrieveLog).where(RetrieveLog.project_id == project_id)).one()
    assert log.params["origin"] == "answer"


def test_retrieve_enriches_filename_and_source_item(*, db_session: Session, settings: Settings) -> None:
    """Check the final rows carry their document's item id and filename."""

    project_id = seed_project(db=db_session, email="enrich@example.com")
    seeded = seed_document_with_chunks(
        db=db_session,
        project_id=project_id,
        chunk_texts=["alpha alpha"],
        filename="report.pdf",
    )
    user = _seed_user(db=db_session)
    result = retrieve(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=RetrieveIn(query="alpha"),
        settings=settings,
    )
    assert len(result) == 1
    chunk = result[0]
    assert chunk.source_item_id == seeded.source_item_id
    assert chunk.filename == "report.pdf"
    assert chunk.position == 0
    assert chunk.text == "alpha alpha"
    assert chunk.chunk_type == "text"
    assert chunk.heading_path == []


def test_retrieve_empty_project_returns_empty_and_logs(*, db_session: Session, settings: Settings) -> None:
    """Check a project with no indexed chunks answers empty and still logs."""

    project_id = seed_project(db=db_session, email="empty@example.com")
    user = _seed_user(db=db_session)
    result = retrieve(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=RetrieveIn(query="alpha"),
        settings=settings,
    )
    assert result == []
    log = db_session.scalars(select(RetrieveLog).where(RetrieveLog.project_id == project_id)).one()
    assert log.stages["final"] == []


def test_zero_norm_query_degrades_to_fts_only(*, db_session: Session, settings: Settings) -> None:
    """Check a zero-norm query vector skips the vector leg and still serves via fts."""

    project_id = seed_project(db=db_session, email="zero-query@example.com")
    seeded = seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["w25 w35 note"])
    user = _seed_user(db=db_session)
    result = retrieve(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        # The stub hash-bag cancels "w25 w35" to the zero vector (verified).
        params=RetrieveIn(query="w25 w35"),
        settings=settings,
    )
    assert [chunk.id for chunk in result] == seeded.chunk_ids
    log = db_session.scalars(select(RetrieveLog).where(RetrieveLog.project_id == project_id)).one()
    assert log.stages["vector"] == []
    assert log.stages["fts"]


def test_zero_norm_embedding_chunk_is_excluded(*, db_session: Session, settings: Settings) -> None:
    """Check a stored zero-norm chunk embedding never surfaces as a NaN score."""

    project_id = seed_project(db=db_session, email="zero-chunk@example.com")
    seeded = seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["w25 w35"])
    user = _seed_user(db=db_session)
    result = retrieve(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=RetrieveIn(query="w25"),
        settings=settings,
    )
    # The vector leg drops the NaN distance row; fts still serves the chunk.
    assert [chunk.id for chunk in result] == seeded.chunk_ids
    log = db_session.scalars(select(RetrieveLog).where(RetrieveLog.project_id == project_id)).one()
    assert log.stages["vector"] == []


def test_retrieve_result_rows_are_retrieved_chunks(*, db_session: Session, settings: Settings) -> None:
    """Check the service returns domain rows, not response schemas."""

    project_id = seed_project(db=db_session, email="rows@example.com")
    seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["alpha"])
    user = _seed_user(db=db_session)
    result = retrieve(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=RetrieveIn(query="alpha"),
        settings=settings,
    )
    assert result
    assert isinstance(result[0], RetrievedChunk)
    assert isinstance(result[0].score, float)
