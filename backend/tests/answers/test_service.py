"""Tests for the answer service, against the real Postgres and the stub LLM."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.answers.prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_DIRECT
from app.answers.schemas import AnswerIn
from app.answers.service import CANNED_EMPTY_ANSWER, Answer, generate_answer
from app.conversations.models import Conversation, ConversationMessage, ConversationMessageChunk
from app.conversations.service import SnapshotIn, append_turn, create_conversation
from app.core.config import Settings
from app.identity.models import User
from app.ingestion.models import Chunk
from app.providers import LLMError
from app.providers.base import RouteDecision
from app.providers.stub_llm import STUB_ANSWER
from app.retrieval.models import RetrieveLog
from app.retrieval.schemas import RetrieveIn
from app.retrieval.service import retrieve
from tests.factories import seed_document_with_chunks, seed_project
from tests.fakes import RaisingLLMProvider, RecordingLLMProvider
from tests.helpers import SettingsForTests


def _seed_user(*, db: Session) -> User:
    """Seed one bare user row so the query log's foreign key resolves."""

    user = User(email=f"{uuid4()}@example.com", password_hash="x")
    db.add(user)
    db.flush()
    return user


def _answer(*, db: Session, project_id: UUID, user_id: UUID, params: AnswerIn, settings: Settings) -> Answer:
    """Call generate_answer and pin the returned answer; the None path has its own test."""

    result = generate_answer(db=db, project_id=project_id, user_id=user_id, params=params, settings=settings)
    assert result is not None
    return result


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
    result = _answer(
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
    result = _answer(
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
    log = db_session.scalars(select(RetrieveLog).where(RetrieveLog.project_id == project_id)).one()
    assert log.params["origin"] == "answer"


def test_request_overrides_beat_settings(*, db_session: Session, settings: Settings) -> None:
    """Check a request top_k override beats the settings default."""

    project_id = seed_project(db=db_session, email="answer-override@example.com")
    seed_document_with_chunks(
        db=db_session, project_id=project_id, chunk_texts=[f"alpha {i}" for i in range(12)]
    )
    user = _seed_user(db=db_session)
    result = _answer(
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
    spread = _answer(
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
    capped = _answer(
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
    result = _answer(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=AnswerIn(query="alpha"),
        settings=SettingsForTests(answer_context_chunks=4),
    )
    # RetrieveIn's own default is 10, so only the setting can produce 4 here.
    assert len(result.chunks) == 4
    assert result.text == STUB_ANSWER


def test_retrieve_route_answers_from_fresh_chunks(
    *, db_session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check a retrieve turn rewrites the query, answers grounded, and persists snapshots."""

    project_id = seed_project(db=db_session, email="s6-retrieve@example.com")
    seeded = seed_document_with_chunks(
        db=db_session, project_id=project_id, chunk_texts=["alpha alpha"], filename="retrieve.pdf"
    )
    user = _seed_user(db=db_session)
    provider = RecordingLLMProvider(
        answer="grounded [1]",
        route_response=RouteDecision(route="retrieve", rewritten_query="alpha standalone"),
    )
    monkeypatch.setattr("app.answers.service.get_llm_provider", lambda *, settings: provider)
    result = _answer(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=AnswerIn(query="alpha"),
        settings=settings,
    )

    assert result.text == "grounded [1]"
    assert result.route == "retrieve"
    assert [chunk.id for chunk in result.chunks] == seeded.chunk_ids
    # The answer call prompts with the grounded system, the raw question, and the blocks.
    system, messages = provider.calls[0]
    assert system == SYSTEM_PROMPT
    assert messages[-1].role == "user"
    assert messages[-1].content.startswith("Question: alpha")
    assert "[1] retrieve.pdf" in messages[-1].content
    # The retrieval ran on the rewritten standalone question, logged with its routing context.
    log = db_session.scalars(select(RetrieveLog).where(RetrieveLog.project_id == project_id)).one()
    assert log.query == "alpha standalone"
    assert log.params["route"] == "retrieve"
    assert log.params["raw_query"] == "alpha"
    assert "router_fallback" not in log.params
    # The turn persisted: two messages, the assistant route, and the snapshot rows.
    conversation_id = db_session.scalars(
        select(Conversation.id).where(Conversation.project_id == project_id)
    ).one()
    assert result.conversation_id == conversation_id
    rows = db_session.scalars(
        select(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id)
    ).all()
    assert [(row.position, row.role, row.route) for row in rows] == [
        (1, "user", None),
        (2, "assistant", "retrieve"),
    ]
    snapshot = db_session.scalars(select(ConversationMessageChunk)).one()
    assert snapshot.chunk_id == seeded.chunk_ids[0]
    assert snapshot.filename == "retrieve.pdf"
    assert snapshot.document_content_hash


def test_direct_route_skips_retrieval_and_logs(
    *, db_session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check a direct turn answers from history alone with no retrieval and no log row."""

    project_id = seed_project(db=db_session, email="s6-direct@example.com")
    seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["alpha"])
    user = _seed_user(db=db_session)
    provider = RecordingLLMProvider(
        answer="from history",
        route_response=RouteDecision(route="direct", rewritten_query=None),
    )
    monkeypatch.setattr("app.answers.service.get_llm_provider", lambda *, settings: provider)
    result = _answer(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=AnswerIn(query="alpha"),
        settings=settings,
    )

    assert result.text == "from history"
    assert result.route == "direct"
    assert result.chunks == []
    system, _messages = provider.calls[0]
    assert system == SYSTEM_PROMPT_DIRECT
    assert db_session.scalars(select(RetrieveLog)).all() == []
    assistant = db_session.scalars(
        select(ConversationMessage).where(ConversationMessage.role == "assistant")
    ).one()
    assert assistant.route == "direct"


def test_reuse_route_gathers_conversation_snapshots(
    *, db_session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check a reuse turn re-uses the conversation's earlier evidence without retrieval."""

    project_id = seed_project(db=db_session, email="s6-reuse@example.com")
    seeded = seed_document_with_chunks(
        db=db_session, project_id=project_id, chunk_texts=["cached passage"], filename="reuse.pdf"
    )
    user = _seed_user(db=db_session)
    conversation = create_conversation(db=db_session, project_id=project_id, user_id=user.id)
    append_turn(
        db=db_session,
        conversation=conversation,
        question="first question",
        answer="first answer [1]",
        route="retrieve",
        snapshots=[
            SnapshotIn(
                chunk_id=seeded.chunk_ids[0],
                filename="reuse.pdf",
                heading_path=["Cached"],
                text="cached passage",
                document_content_hash="hash-cached",
            )
        ],
    )
    provider = RecordingLLMProvider(
        answer="reused [1]",
        route_response=RouteDecision(route="reuse", rewritten_query=None),
    )
    monkeypatch.setattr("app.answers.service.get_llm_provider", lambda *, settings: provider)
    result = _answer(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=AnswerIn(query="follow-up"),
        settings=settings,
    )

    assert result.route == "reuse"
    assert db_session.scalars(select(RetrieveLog)).all() == []
    # The answer re-uses the gathered snapshot rows, not fresh retrieval.
    assert [
        chunk.chunk_id for chunk in result.chunks if isinstance(chunk, ConversationMessageChunk)
    ] == seeded.chunk_ids
    # The router call and the answer call see the same gathered evidence (Focus 4).
    _route_system, route_messages = provider.route_calls[0]
    assert any(
        "EVIDENCE SUMMARY" in message.content and "reuse.pdf" in message.content for message in route_messages
    )
    _answer_system, answer_messages = provider.calls[0]
    final = answer_messages[-1]
    assert final.content.startswith("Question: follow-up")
    assert "[1] reuse.pdf - Cached" in final.content
    assert "cached passage" in final.content


def test_reuse_with_zero_snapshots_falls_back_to_retrieve(
    *, db_session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check a reuse turn with nothing gathered degrades to retrieval with the raw question."""

    project_id = seed_project(db=db_session, email="s6-reuse-empty@example.com")
    seed_document_with_chunks(
        db=db_session, project_id=project_id, chunk_texts=["alpha alpha"], filename="fallback.pdf"
    )
    user = _seed_user(db=db_session)
    provider = RecordingLLMProvider(
        answer="fallback grounded [1]",
        route_response=RouteDecision(route="reuse", rewritten_query=None),
    )
    monkeypatch.setattr("app.answers.service.get_llm_provider", lambda *, settings: provider)
    result = _answer(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=AnswerIn(query="alpha"),
        settings=settings,
    )

    log = db_session.scalars(select(RetrieveLog).where(RetrieveLog.project_id == project_id)).one()
    assert log.query == "alpha"
    assert log.params["route"] == "retrieve"
    assert result.route == "retrieve"
    assert result.chunks


def test_router_error_falls_back_to_retrieve_raw(
    *, db_session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check a failed router call retrieves the raw question and logs the fallback (Focus 3)."""

    project_id = seed_project(db=db_session, email="s6-fallback@example.com")
    seed_document_with_chunks(
        db=db_session, project_id=project_id, chunk_texts=["alpha alpha"], filename="fallback.pdf"
    )
    user = _seed_user(db=db_session)
    provider = RecordingLLMProvider(answer="fallback answer [1]", route_error=True)
    monkeypatch.setattr("app.answers.service.get_llm_provider", lambda *, settings: provider)
    result = _answer(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=AnswerIn(query="alpha"),
        settings=settings,
    )

    log = db_session.scalars(select(RetrieveLog).where(RetrieveLog.project_id == project_id)).one()
    assert log.query == "alpha"
    assert log.params["route"] == "retrieve"
    assert log.params["raw_query"] == "alpha"
    assert log.params["router_fallback"] == "true"
    assert result.route == "retrieve"


def test_failed_answer_call_persists_nothing(
    *, db_session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check a failed generate leaves no conversation, not even an empty one."""

    project_id = seed_project(db=db_session, email="s6-nothing@example.com")
    seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["alpha"])
    user = _seed_user(db=db_session)
    monkeypatch.setattr("app.answers.service.get_llm_provider", lambda *, settings: RaisingLLMProvider())
    with pytest.raises(LLMError):
        generate_answer(
            db=db_session,
            project_id=project_id,
            user_id=user.id,
            params=AnswerIn(query="alpha"),
            settings=settings,
        )
    assert db_session.scalars(select(Conversation).where(Conversation.project_id == project_id)).all() == []
    assert db_session.scalars(select(ConversationMessage)).all() == []


def test_conversation_id_null_resolves_latest(*, db_session: Session, settings: Settings) -> None:
    """Check a null conversation_id appends to the caller's latest conversation."""

    project_id = seed_project(db=db_session, email="s6-latest@example.com")
    user = _seed_user(db=db_session)
    created = create_conversation(db=db_session, project_id=project_id, user_id=user.id)
    result = _answer(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=AnswerIn(query="alpha", conversation_id=None),
        settings=settings,
    )
    assert result is not None
    assert result.conversation_id == created.id
    count = db_session.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.project_id == project_id)
    )
    assert count == 1


def test_foreign_conversation_id_returns_none(*, db_session: Session, settings: Settings) -> None:
    """Check another user's conversation id resolves to None for the 404."""

    project_id = seed_project(db=db_session, email="s6-foreign@example.com")
    owner = _seed_user(db=db_session)
    stranger = _seed_user(db=db_session)
    created = create_conversation(db=db_session, project_id=project_id, user_id=owner.id)
    result = generate_answer(
        db=db_session,
        project_id=project_id,
        user_id=stranger.id,
        params=AnswerIn(query="alpha", conversation_id=created.id),
        settings=settings,
    )
    assert result is None


def test_reuse_answers_from_snapshots_after_chunk_replacement(
    *, db_session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check REUSE answers from the inline snapshot once the cited chunk row is gone (Focus 5)."""

    project_id = seed_project(db=db_session, email="s6-reuse-stale@example.com")
    seeded = seed_document_with_chunks(
        db=db_session, project_id=project_id, chunk_texts=["durable inline"], filename="stale.pdf"
    )
    user = _seed_user(db=db_session)
    conversation = create_conversation(db=db_session, project_id=project_id, user_id=user.id)
    append_turn(
        db=db_session,
        conversation=conversation,
        question="first question",
        answer="first answer [1]",
        route="retrieve",
        snapshots=[
            SnapshotIn(
                chunk_id=seeded.chunk_ids[0],
                filename="stale.pdf",
                heading_path=[],
                text="durable inline",
                document_content_hash="hash-durable",
            )
        ],
    )
    # Re-ingestion replaces the chunk row: the snapshot survives with a null link.
    db_session.execute(delete(Chunk).where(Chunk.id == seeded.chunk_ids[0]))
    db_session.commit()
    db_session.expire_all()

    provider = RecordingLLMProvider(
        answer="stale but readable [1]",
        route_response=RouteDecision(route="reuse", rewritten_query=None),
    )
    monkeypatch.setattr("app.answers.service.get_llm_provider", lambda *, settings: provider)
    result = _answer(
        db=db_session,
        project_id=project_id,
        user_id=user.id,
        params=AnswerIn(query="what did it say?", conversation_id=conversation.id),
        settings=settings,
    )

    assert result.route == "reuse"
    assert db_session.scalars(select(RetrieveLog)).all() == []
    # The answer grounded in the inline snapshot text, never in a live chunk.
    _system, messages = provider.calls[0]
    final = messages[-1]
    assert final.content.startswith("Question: what did it say?")
    assert "[1] stale.pdf" in final.content
    assert "durable inline" in final.content
    assert [chunk.chunk_id for chunk in result.chunks if isinstance(chunk, ConversationMessageChunk)] == [
        None
    ]
    # The new assistant turn's snapshot row also carries the null link and the text.
    assistant = db_session.scalars(
        select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation.id,
            ConversationMessage.position == 4,
        )
    ).one()
    snapshot = db_session.scalars(
        select(ConversationMessageChunk).where(ConversationMessageChunk.message_id == assistant.id)
    ).one()
    assert snapshot.chunk_id is None
    assert snapshot.text == "durable inline"
