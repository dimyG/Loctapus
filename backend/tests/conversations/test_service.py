"""Tests for the conversations service, against the real Postgres."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.conversations.models import Conversation, ConversationMessage, ConversationMessageChunk
from app.conversations.service import (
    SnapshotIn,
    append_turn,
    create_conversation,
    gather_snapshots,
    get_latest_conversation,
    load_history,
    resolve_conversation,
)
from app.identity.models import User
from app.ingestion.models import Chunk
from tests.factories import seed_document_with_chunks, seed_project


def _seed_user(*, db: Session) -> User:
    """Seed one bare user row so the conversation's user foreign key resolves."""

    user = User(email=f"{uuid4()}@example.com", password_hash="x")
    db.add(user)
    db.flush()
    return user


def _snapshot(*, text: str, chunk_id: UUID | None = None, filename: str = "doc.pdf") -> SnapshotIn:
    """Build one snapshot input; only the persisted fields matter."""

    return SnapshotIn(
        chunk_id=chunk_id,
        filename=filename,
        heading_path=["Intro"],
        text=text,
        document_content_hash=f"hash-{text}",
    )


def test_create_and_get_latest_round_trip(*, db_session: Session) -> None:
    """Check create then latest returns the same row with a non-null last_message_at."""

    project_id = seed_project(db=db_session, email="conv@example.com")
    user = _seed_user(db=db_session)
    conversation = create_conversation(db=db_session, project_id=project_id, user_id=user.id)
    latest = get_latest_conversation(db=db_session, project_id=project_id, user_id=user.id)
    assert latest is not None
    assert latest.id == conversation.id
    assert latest.user_id == user.id
    assert latest.last_message_at is not None


def test_get_latest_none_when_user_has_no_conversation(*, db_session: Session) -> None:
    """Check a user with no conversation gets None, never another user's row."""

    project_id = seed_project(db=db_session, email="conv-none@example.com")
    other = _seed_user(db=db_session)
    create_conversation(db=db_session, project_id=project_id, user_id=other.id)
    user = _seed_user(db=db_session)
    assert get_latest_conversation(db=db_session, project_id=project_id, user_id=user.id) is None


def test_resolve_null_creates_pending_row_when_none_exists(*, db_session: Session) -> None:
    """Check a null conversation_id with no prior row resolves to a matching new row."""

    project_id = seed_project(db=db_session, email="conv-new@example.com")
    user = _seed_user(db=db_session)
    conversation = resolve_conversation(
        db=db_session, project_id=project_id, user_id=user.id, conversation_id=None
    )
    assert conversation is not None
    assert conversation.project_id == project_id
    assert conversation.user_id == user.id
    # The new row stays pending (no id yet): it joins the append transaction, never a read.
    assert conversation.id is None


def test_resolve_null_reuses_latest_conversation(*, db_session: Session) -> None:
    """Check a null conversation_id racing hydration appends to the existing row (Focus 1)."""

    project_id = seed_project(db=db_session, email="conv-race@example.com")
    user = _seed_user(db=db_session)
    created = create_conversation(db=db_session, project_id=project_id, user_id=user.id)
    resolved = resolve_conversation(
        db=db_session, project_id=project_id, user_id=user.id, conversation_id=None
    )
    assert resolved is not None
    assert resolved.id == created.id
    count = db_session.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.user_id == user.id)
    )
    assert count == 1


def test_resolve_explicit_rejects_foreign_conversation(*, db_session: Session) -> None:
    """Check an explicit id resolves only for its owner inside its own project."""

    project_id = seed_project(db=db_session, email="conv-owner@example.com")
    other_project_id = seed_project(db=db_session, email="conv-other-project@example.com")
    owner = _seed_user(db=db_session)
    stranger = _seed_user(db=db_session)
    created = create_conversation(db=db_session, project_id=project_id, user_id=owner.id)

    stranger_view = resolve_conversation(
        db=db_session, project_id=project_id, user_id=stranger.id, conversation_id=created.id
    )
    assert stranger_view is None

    cross_project = resolve_conversation(
        db=db_session, project_id=other_project_id, user_id=owner.id, conversation_id=created.id
    )
    assert cross_project is None

    own = resolve_conversation(
        db=db_session, project_id=project_id, user_id=owner.id, conversation_id=created.id
    )
    assert own is not None
    assert own.id == created.id


def test_append_turn_writes_messages_snapshots_and_bumps(*, db_session: Session) -> None:
    """Check one append writes both messages, their snapshots, and the recency bump."""

    project_id = seed_project(db=db_session, email="conv-append@example.com")
    user = _seed_user(db=db_session)
    before = datetime.now(UTC)
    # A pending row: the conversation creation must join this append transaction.
    conversation = resolve_conversation(
        db=db_session, project_id=project_id, user_id=user.id, conversation_id=None
    )
    assert conversation is not None
    append_turn(
        db=db_session,
        conversation=conversation,
        question="what is alpha?",
        answer="alpha is a letter. [1]",
        route="retrieve",
        snapshots=[_snapshot(text="alpha is a letter")],
    )

    messages = db_session.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(ConversationMessage.position)
    ).all()
    assert [(message.position, message.role) for message in messages] == [
        (1, "user"),
        (2, "assistant"),
    ]
    assert messages[0].content == "what is alpha?"
    assert messages[0].route is None
    assert messages[1].content == "alpha is a letter. [1]"
    assert messages[1].route == "retrieve"

    snapshot = db_session.scalars(
        select(ConversationMessageChunk).where(ConversationMessageChunk.message_id == messages[1].id)
    ).one()
    assert snapshot.ordinal == 1
    assert snapshot.filename == "doc.pdf"
    assert snapshot.text == "alpha is a letter"
    assert snapshot.document_content_hash == "hash-alpha is a letter"

    persisted = db_session.get_one(Conversation, conversation.id)
    assert persisted.last_message_at >= before


def test_append_turn_concurrent_sends_serialize(*, engine: Engine) -> None:
    """Check two concurrent appends on one conversation land four distinct positions (Focus 2)."""

    factory = sessionmaker(bind=engine)
    setup = factory()
    try:
        project_id = seed_project(db=setup, email="conv-concurrent@example.com")
        user = _seed_user(db=setup)
        conversation = create_conversation(db=setup, project_id=project_id, user_id=user.id)
        conversation_id = conversation.id
    finally:
        setup.close()

    def send(*, index: int) -> None:
        """Append one turn through a private session so the row lock serializes for real."""

        session = factory()
        try:
            append_turn(
                db=session,
                conversation=session.get_one(Conversation, conversation_id),
                question=f"question {index}",
                answer=f"answer {index}",
                route="direct",
                snapshots=[],
            )
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(send, index=index) for index in range(2)]
        for future in futures:
            future.result()

    verify = factory()
    try:
        positions = verify.scalars(
            select(ConversationMessage.position).where(ConversationMessage.conversation_id == conversation_id)
        ).all()
    finally:
        verify.close()
    assert sorted(positions) == [1, 2, 3, 4]

    # The committed rows live outside the rollback-managed fixture, so clean them up.
    cleanup = factory()
    try:
        cleanup.execute(delete(Conversation).where(Conversation.id == conversation_id))
        cleanup.commit()
    finally:
        cleanup.close()


def test_gather_snapshots_dedupes_and_caps(*, db_session: Session) -> None:
    """Check gathering walks newest-first, dedupes, and caps at the request (Focus 4)."""

    project_id = seed_project(db=db_session, email="conv-gather@example.com")
    user = _seed_user(db=db_session)
    seeded = seed_document_with_chunks(
        db=db_session, project_id=project_id, chunk_texts=["one", "two", "three"]
    )
    conversation = create_conversation(db=db_session, project_id=project_id, user_id=user.id)
    # The older turn cites chunks one and two; the newer turn cites two and three.
    append_turn(
        db=db_session,
        conversation=conversation,
        question="older question",
        answer="older answer [1] [2]",
        route="retrieve",
        snapshots=[
            _snapshot(text="one", chunk_id=seeded.chunk_ids[0]),
            _snapshot(text="two", chunk_id=seeded.chunk_ids[1]),
            _snapshot(text="ghost"),
        ],
    )
    append_turn(
        db=db_session,
        conversation=conversation,
        question="newer question",
        answer="newer answer [1] [2]",
        route="reuse",
        snapshots=[
            _snapshot(text="two", chunk_id=seeded.chunk_ids[1]),
            _snapshot(text="three", chunk_id=seeded.chunk_ids[2]),
            _snapshot(text="ghost"),
        ],
    )

    gathered = gather_snapshots(db=db_session, conversation_id=conversation.id, max_chunks=5)
    assert [row.chunk_id for row in gathered] == [
        seeded.chunk_ids[1],
        seeded.chunk_ids[2],
        None,
        seeded.chunk_ids[0],
    ]

    capped = gather_snapshots(db=db_session, conversation_id=conversation.id, max_chunks=2)
    assert [row.chunk_id for row in capped] == [seeded.chunk_ids[1], seeded.chunk_ids[2]]


def test_snapshot_survives_chunk_replacement(*, db_session: Session) -> None:
    """Check a deleted chunk nulls the snapshot instead of cascading it away (Focus 5)."""

    project_id = seed_project(db=db_session, email="conv-stale@example.com")
    user = _seed_user(db=db_session)
    seeded = seed_document_with_chunks(db=db_session, project_id=project_id, chunk_texts=["durable text"])
    conversation = create_conversation(db=db_session, project_id=project_id, user_id=user.id)
    append_turn(
        db=db_session,
        conversation=conversation,
        question="question",
        answer="answer [1]",
        route="retrieve",
        snapshots=[_snapshot(text="durable text", chunk_id=seeded.chunk_ids[0])],
    )
    snapshot_id = db_session.scalars(select(ConversationMessageChunk.id)).one()

    db_session.execute(delete(Chunk).where(Chunk.id == seeded.chunk_ids[0]))
    db_session.commit()
    db_session.expire_all()

    snapshot = db_session.get_one(ConversationMessageChunk, snapshot_id)
    assert snapshot.chunk_id is None
    assert snapshot.text == "durable text"


def test_load_history_strips_citation_markers(*, db_session: Session) -> None:
    """Check history returns the last messages oldest-first with markers stripped."""

    project_id = seed_project(db=db_session, email="conv-history@example.com")
    user = _seed_user(db=db_session)
    conversation = create_conversation(db=db_session, project_id=project_id, user_id=user.id)
    append_turn(
        db=db_session,
        conversation=conversation,
        question="first question",
        answer="first answer [1]",
        route="direct",
        snapshots=[],
    )
    append_turn(
        db=db_session,
        conversation=conversation,
        question="second question",
        answer="second answer [1] [2]",
        route="retrieve",
        snapshots=[],
    )

    history = load_history(db=db_session, conversation_id=conversation.id, limit=4)
    assert [(message.role, message.content) for message in history] == [
        ("user", "first question"),
        ("assistant", "first answer"),
        ("user", "second question"),
        ("assistant", "second answer"),
    ]

    trimmed = load_history(db=db_session, conversation_id=conversation.id, limit=2)
    assert [(message.role, message.content) for message in trimmed] == [
        ("user", "second question"),
        ("assistant", "second answer"),
    ]
