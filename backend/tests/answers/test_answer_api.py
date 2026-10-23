"""Tests for the answer HTTP endpoint."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.answers.service import CANNED_EMPTY_ANSWER
from app.ingestion.models import Document
from app.providers.stub_llm import STUB_ANSWER
from app.retrieval.models import RetrieveLog
from tests.factories import seed_document_with_chunks
from tests.fakes import RaisingLLMProvider
from tests.helpers import _auth, _default_team_id


def _create_project(*, client: TestClient, email: str) -> tuple[dict[str, str], str]:
    """Register one account and create one named project; return its auth headers and id."""

    headers = _auth(client=client, email=email)
    team_id = _default_team_id(client=client, headers=headers)
    response = client.post(
        "/api/projects", json={"name": f"answer-{email}", "team_id": team_id}, headers=headers
    )
    return headers, str(response.json()["id"])


def test_answer_requires_auth(*, client: TestClient) -> None:
    """Check the endpoint answers 401 without a bearer token."""

    response = client.post(f"/api/projects/{uuid4()}/answer", json={"query": "alpha"})
    assert response.status_code == 401


def test_answer_404_for_invisible_project(*, client: TestClient) -> None:
    """Check a non-member gets 404 for another user's private project."""

    _headers, project_id = _create_project(client=client, email="alice-404@example.com")
    bob_headers = _auth(client=client, email="bob-404@example.com")
    response = client.post(f"/api/projects/{project_id}/answer", json={"query": "alpha"}, headers=bob_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "project not found"


def test_answer_works_for_public_project_non_member(*, client: TestClient, db_session: Session) -> None:
    """Check a non-member can ask about a project the owner made public."""

    alice_headers, project_id = _create_project(client=client, email="alice-pub@example.com")
    seed_document_with_chunks(
        db=db_session, project_id=UUID(project_id), chunk_texts=["alpha"], filename="pub.pdf"
    )
    made_public = client.patch(f"/api/projects/{project_id}", json={"is_public": True}, headers=alice_headers)
    assert made_public.status_code == 200
    bob_headers = _auth(client=client, email="bob-pub@example.com")
    response = client.post(f"/api/projects/{project_id}/answer", json={"query": "alpha"}, headers=bob_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == STUB_ANSWER
    assert body["chunks"]


@pytest.mark.parametrize(
    "body",
    [
        {"query": "   "},
        {"query": "x" * 2001},
        {"query": "\u0000x"},
        {"query": "x", "top_k": 0},
        {"query": "x", "top_k": 51},
        {"query": "x", "max_chunks_per_document": 0},
        {"query": "x", "conversation_id": "not-a-uuid"},
    ],
)
def test_answer_validation_errors(*, client: TestClient, body: dict[str, object]) -> None:
    """Check malformed bodies answer 422."""

    headers, project_id = _create_project(client=client, email=f"val-{uuid4()}@example.com")
    response = client.post(f"/api/projects/{project_id}/answer", json=body, headers=headers)
    assert response.status_code == 422


def test_answer_strips_and_matches(*, client: TestClient, db_session: Session) -> None:
    """Check a padded query strips and still matches its chunk."""

    headers, project_id = _create_project(client=client, email="strip@example.com")
    seed_document_with_chunks(db=db_session, project_id=UUID(project_id), chunk_texts=["alpha alpha"])
    response = client.post(f"/api/projects/{project_id}/answer", json={"query": "  alpha  "}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["chunks"][0]["text"] == "alpha alpha"
    assert body["answer"] == STUB_ANSWER


def test_rerank_true_accepted_and_ignored(*, client: TestClient, db_session: Session) -> None:
    """Check the rerank flag is accepted and changes nothing until the S6 reranker."""

    headers, project_id = _create_project(client=client, email="rerank@example.com")
    seed_document_with_chunks(
        db=db_session, project_id=UUID(project_id), chunk_texts=["alpha", "bravo alpha"]
    )
    without = client.post(f"/api/projects/{project_id}/answer", json={"query": "alpha"}, headers=headers)
    with_flag = client.post(
        f"/api/projects/{project_id}/answer",
        json={"query": "alpha", "rerank": True},
        headers=headers,
    )
    assert without.status_code == 200
    assert with_flag.status_code == 200
    assert with_flag.json() == without.json()


def test_answer_empty_project_returns_canned(*, client: TestClient, db_session: Session) -> None:
    """Check a project with no indexed chunks answers from the can and logs exactly once."""

    headers, project_id = _create_project(client=client, email="empty-api@example.com")
    response = client.post(f"/api/projects/{project_id}/answer", json={"query": "alpha"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == CANNED_EMPTY_ANSWER
    assert body["route"] == "retrieve"
    assert body["chunks"] == []
    logs = db_session.scalars(select(RetrieveLog).where(RetrieveLog.project_id == UUID(project_id))).all()
    assert len(logs) == 1


def test_answer_with_conversation_id_round_trips(*, client: TestClient, db_session: Session) -> None:
    """Check the served conversation id threads a second ask into the same conversation."""

    headers, project_id = _create_project(client=client, email="round@example.com")
    seed_document_with_chunks(db=db_session, project_id=UUID(project_id), chunk_texts=["alpha"])
    first = client.post(f"/api/projects/{project_id}/answer", json={"query": "alpha"}, headers=headers)
    assert first.status_code == 200
    conversation_id = first.json()["conversation_id"]

    second = client.post(
        f"/api/projects/{project_id}/answer",
        json={"query": "alpha again", "conversation_id": conversation_id},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id

    latest = client.get(f"/api/projects/{project_id}/conversations/latest", headers=headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["conversation_id"] == conversation_id
    assert [message["role"] for message in body["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_answer_404_unknown_conversation(*, client: TestClient) -> None:
    """Check an unowned conversation id answers 404 instead of answering."""

    headers, project_id = _create_project(client=client, email="unknown-conv@example.com")
    response = client.post(
        f"/api/projects/{project_id}/answer",
        json={"query": "alpha", "conversation_id": str(uuid4())},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "conversation not found"


def test_answer_response_shape(*, client: TestClient, db_session: Session) -> None:
    """Check the response carries exactly the served fields."""

    headers, project_id = _create_project(client=client, email="shape@example.com")
    seeded = seed_document_with_chunks(
        db=db_session,
        project_id=UUID(project_id),
        chunk_texts=["alpha alpha"],
        filename="shape.pdf",
    )
    db_content_hash = db_session.get_one(Document, seeded.document_id).content_hash
    response = client.post(
        f"/api/projects/{project_id}/answer",
        json={"query": "alpha", "top_k": 5},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"answer", "route", "conversation_id", "chunks"}
    assert body["answer"] == STUB_ANSWER
    assert body["route"] == "retrieve"
    assert body["conversation_id"]
    assert len(body["chunks"]) == 1
    item = body["chunks"][0]
    assert set(item) == {"chunk_id", "filename", "heading_path", "text", "document_content_hash"}
    assert item["chunk_id"] == str(seeded.chunk_ids[0])
    assert item["filename"] == "shape.pdf"
    assert item["heading_path"] == []
    assert item["text"] == "alpha alpha"
    assert item["document_content_hash"] == db_content_hash


def test_llm_failure_maps_to_502_and_still_logs(
    *, client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check a provider failure answers 502 while the answer-origin log row survives."""

    headers, project_id = _create_project(client=client, email="llm-down@example.com")
    seed_document_with_chunks(db=db_session, project_id=UUID(project_id), chunk_texts=["alpha"])
    monkeypatch.setattr("app.answers.service.get_llm_provider", lambda *, settings: RaisingLLMProvider())
    response = client.post(f"/api/projects/{project_id}/answer", json={"query": "alpha"}, headers=headers)
    assert response.status_code == 502
    assert response.json()["detail"] == "The answer service is down for maintenance."
    log = db_session.scalars(select(RetrieveLog).where(RetrieveLog.project_id == UUID(project_id))).one()
    assert log.params["origin"] == "answer"


def test_error_paths_log_nothing(*, client: TestClient, db_session: Session) -> None:
    """Check the 401, 404, and 422 paths never write a query log row."""

    alice_headers, project_id = _create_project(client=client, email="alice-logs@example.com")
    stranger_headers = _auth(client=client, email="stranger-logs@example.com")
    unauthed = client.post(f"/api/projects/{project_id}/answer", json={"query": "alpha"})
    forbidden = client.post(
        f"/api/projects/{project_id}/answer", json={"query": "alpha"}, headers=stranger_headers
    )
    invalid = client.post(f"/api/projects/{project_id}/answer", json={"query": "   "}, headers=alice_headers)
    assert unauthed.status_code == 401
    assert forbidden.status_code == 404
    assert invalid.status_code == 422
    assert db_session.scalars(select(RetrieveLog)).all() == []
