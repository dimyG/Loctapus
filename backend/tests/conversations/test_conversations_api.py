"""Tests for the conversations HTTP endpoints."""

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.conversations.models import Conversation
from app.conversations.service import SnapshotIn, append_turn
from tests.helpers import _auth, _default_team_id


def _create_project(*, client: TestClient, email: str) -> tuple[dict[str, str], str]:
    """Register one account and create one named project; return its auth headers and id."""

    headers = _auth(client=client, email=email)
    team_id = _default_team_id(client=client, headers=headers)
    response = client.post(
        "/api/projects", json={"name": f"conversations-{email}", "team_id": team_id}, headers=headers
    )
    return headers, str(response.json()["id"])


def _snapshot(*, text: str) -> SnapshotIn:
    """Build one snapshot input for seeding a hydrated thread."""

    return SnapshotIn(
        chunk_id=None,
        filename="doc.pdf",
        heading_path=["Intro"],
        text=text,
        document_content_hash="hash-1",
    )


def test_post_conversations_creates_owned_empty_conversation(*, client: TestClient) -> None:
    """Check POST creates the caller's empty conversation and a stranger sees none."""

    headers, project_id = _create_project(client=client, email="alice-create@example.com")
    response = client.post(f"/api/projects/{project_id}/conversations", headers=headers)
    assert response.status_code == 201
    conversation_id = response.json()["conversation_id"]

    latest = client.get(f"/api/projects/{project_id}/conversations/latest", headers=headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["conversation_id"] == conversation_id
    assert body["messages"] == []

    stranger_headers = _auth(client=client, email="bob-create@example.com")
    stranger_latest = client.get(f"/api/projects/{project_id}/conversations/latest", headers=stranger_headers)
    assert stranger_latest.status_code == 404
    assert stranger_latest.json()["detail"] == "project not found"


def test_get_latest_returns_messages_in_order_with_chunks(*, client: TestClient, db_session: Session) -> None:
    """Check the hydrated thread carries ordered messages with their snapshots."""

    headers, project_id = _create_project(client=client, email="alice-thread@example.com")
    created = client.post(f"/api/projects/{project_id}/conversations", headers=headers)
    conversation_id = UUID(created.json()["conversation_id"])
    conversation = db_session.get_one(Conversation, conversation_id)
    append_turn(
        db=db_session,
        conversation=conversation,
        question="first question",
        answer="first answer [1]",
        route="retrieve",
        snapshots=[_snapshot(text="first passage")],
    )
    append_turn(
        db=db_session,
        conversation=conversation,
        question="second question",
        answer="second answer",
        route="reuse",
        snapshots=[],
    )

    latest = client.get(f"/api/projects/{project_id}/conversations/latest", headers=headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["conversation_id"] == str(conversation_id)
    assert [(message["role"], message["content"], message["route"]) for message in body["messages"]] == [
        ("user", "first question", None),
        ("assistant", "first answer [1]", "retrieve"),
        ("user", "second question", None),
        ("assistant", "second answer", "reuse"),
    ]
    assert body["messages"][1]["chunks"] == [
        {
            "chunk_id": None,
            "filename": "doc.pdf",
            "heading_path": ["Intro"],
            "text": "first passage",
            "document_content_hash": "hash-1",
        }
    ]
    assert body["messages"][0]["chunks"] == []


def test_get_latest_404_when_none(*, client: TestClient) -> None:
    """Check latest answers 404 with a friendly detail before any conversation exists."""

    headers, project_id = _create_project(client=client, email="alice-empty@example.com")
    response = client.get(f"/api/projects/{project_id}/conversations/latest", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "no conversation yet"


def test_post_and_get_latest_404_on_invisible_project(*, client: TestClient) -> None:
    """Check both endpoints answer 404 for a project the caller cannot see."""

    _headers, project_id = _create_project(client=client, email="alice-hidden@example.com")
    stranger_headers = _auth(client=client, email="bob-hidden@example.com")
    post = client.post(f"/api/projects/{project_id}/conversations", headers=stranger_headers)
    assert post.status_code == 404
    assert post.json()["detail"] == "project not found"
    latest = client.get(f"/api/projects/{project_id}/conversations/latest", headers=stranger_headers)
    assert latest.status_code == 404
    assert latest.json()["detail"] == "project not found"


def test_routes_require_auth(*, client: TestClient) -> None:
    """Check both endpoints answer 401 without a bearer token."""

    project_id = uuid4()
    post = client.post(f"/api/projects/{project_id}/conversations")
    assert post.status_code == 401
    latest = client.get(f"/api/projects/{project_id}/conversations/latest")
    assert latest.status_code == 401
