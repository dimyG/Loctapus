"""Tests for the answer service, against the real Postgres and the stub LLM."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.answers.schemas import AnswerIn
from app.answers.service import CANNED_EMPTY_ANSWER, generate_answer
from app.core.config import Settings
from app.identity.models import User
from app.providers.stub_llm import STUB_ANSWER
from app.retrieval.models import QueryLog
from app.retrieval.schemas import RetrieveIn
from app.retrieval.service import retrieve
from tests.factories import seed_document_with_chunks, seed_project
from tests.fakes import RecordingLLMProvider
from tests.helpers import SettingsForTests


def _seed_user(*, db: Session) -> User:
    """Seed one bare user row so the query log's foreign key resolves."""

    user = User(email=f"{uuid4()}@example.com", password_hash="x")
    db.add(user)
    db.flush()
    return user


def test_answer_chunks_equal_retrieval_final_chunks(*, db_session: Session, settings: Settings) -> None:
    """Check the answer grounds in exactly the chunks the answer-origin retrieve returns."""

    project_id = seed_project(db=db_session, email="answer-chunks@example.com")
    seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["alpha alpha"])
    user = _seed_user(db=db_session)
    expected = retrieve(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=RetrieveIn(query="alpha", top_k=10, max_chunks_per_document=3),
        settings=settings,
        origin="answer",
    )
    result = generate_answer(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=AnswerIn(query="alpha"),
        settings=settings,
    )
    assert result.text == STUB_ANSWER
    assert [chunk.id for chunk in result.chunks] == [chunk.id for chunk in expected]


def test_empty_index_returns_canned_answer_without_llm_call(
    *, db_session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check an empty index answers from the can and never calls the LLM."""

    project_id = seed_project(db=db_session, email="answer-empty@example.com")
    user = _seed_user(db=db_session)
    provider = RecordingLLMProvider(answer="never served")
    monkeypatch.setattr("app.answers.service.get_llm_provider", lambda *, settings: provider)
    result = generate_answer(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=AnswerIn(query="alpha"),
        settings=settings,
    )
    assert result.text == CANNED_EMPTY_ANSWER
    assert result.chunks == []
    assert provider.calls == []


def test_answer_logs_origin_answer(*, db_session: Session, settings: Settings) -> None:
    """Check the answer round labels its query log row with the answer origin."""

    project_id = seed_project(db=db_session, email="answer-origin@example.com")
    seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["alpha"])
    user = _seed_user(db=db_session)
    generate_answer(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=AnswerIn(query="alpha"),
        settings=settings,
    )
    log = db_session.scalars(select(QueryLog).where(QueryLog.project_id == project_id)).one()
    assert log.params["origin"] == "answer"


def test_request_overrides_beat_settings(*, db_session: Session, settings: Settings) -> None:
    """Check a request top_k override beats the settings default."""

    project_id = seed_project(db=db_session, email="answer-override@example.com")
    seed_document_with_chunks(
        db=db_session, project_id=project_id, chunk_texts=[f"alpha {i}" for i in range(12)]
    )
    user = _seed_user(db=db_session)
    result = generate_answer(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=AnswerIn(query="alpha", top_k=2),
        settings=settings,
    )
    assert len(result.chunks) == 2
    assert result.text == STUB_ANSWER


def test_settings_defaults_apply_when_request_omits(*, db_session: Session, settings: Settings) -> None:
    """Check omitted request overrides resolve against the answer settings defaults."""

    spread_project = seed_project(db=db_session, email="answer-defaults@example.com")
    for doc in range(4):
        seed_document_with_chunks(
            db=db_session,
            project_id=spread_project,
            chunk_texts=[f"alpha {doc} {i}" for i in range(3)],
            filename=f"defaults-{doc}.pdf",
        )
    user = _seed_user(db=db_session)
    spread = generate_answer(
        db=db_session,
        project_id=spread_project,
        user_id=user.id,
        params=AnswerIn(query="alpha"),
        settings=settings,
    )
    # Pins the total at the default value (10); the sibling test below proves the source is
    # the setting, not RetrieveIn's own coincidental default of 10.
    assert len(spread.chunks) == 10
    capped_project = seed_project(db=db_session, email="answer-capped@example.com")
    seed_document_with_chunks(
        db=db_session,
        project_id=capped_project,
        chunk_texts=[f"alpha {i}" for i in range(5)],
        filename="capped.pdf",
    )
    capped = generate_answer(
        db=db_session,
        project_id=capped_project,
        user_id=user.id,
        params=AnswerIn(query="alpha"),
        settings=settings,
    )
    # answer_max_chunks_per_document (3) caps a document that top_k=10 alone would not.
    assert len(capped.chunks) == 3


def test_settings_answer_context_chunks_caps_when_request_omits(*, db_session: Session) -> None:
    """Check a non-default answer_context_chunks setting caps an omitted request top_k."""

    project_id = seed_project(db=db_session, email="answer-setting-source@example.com")
    for doc in range(4):
        seed_document_with_chunks(
            db=db_session,
            project_id=project_id,
            chunk_texts=[f"alpha {doc} {i}" for i in range(3)],
            filename=f"setting-source-{doc}.pdf",
        )
    user = _seed_user(db=db_session)
    result = generate_answer(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=AnswerIn(query="alpha"),
        settings=SettingsForTests(answer_context_chunks=4),
    )
    # RetrieveIn's own default is 10, so only the setting can produce 4 here.
    assert len(result.chunks) == 4
    assert result.text == STUB_ANSWER
