"""Tests for the retrieval HTTP endpoint."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.retrieval.models import QueryLog
from tests.factories import seed_document_with_chunks
from tests.helpers import _auth, _default_team_id


def _create_project(*, client: TestClient, email: str) -> tuple[dict[str, str], str]:
    """Register one account and create one named project; return its auth headers and id."""

    headers = _auth(client=client, email=email)
    team_id = _default_team_id(client=client, headers=headers)
    response = client.post(
        "/api/projects", json={"name": f"retrieval-{email}", "team_id": team_id}, headers=headers
    )
    return headers, str(response.json()["id"])


def test_retrieve_requires_auth(*, client: TestClient) -> None:
    """Check the endpoint answers 401 without a bearer token."""

    response = client.post(f"/api/projects/{uuid4()}/retrieve", json={"query": "alpha"})
    assert response.status_code == 401


def test_retrieve_404_for_invisible_project(*, client: TestClient) -> None:
    """Check a non-member gets 404 for another user's private project."""

    _headers, project_id = _create_project(client=client, email="alice-404@example.com")
    bob_headers = _auth(client=client, email="bob-404@example.com")
    response = client.post(
        f"/api/projects/{project_id}/retrieve", json={"query": "alpha"}, headers=bob_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "project not found"


def test_retrieve_works_for_public_project_non_member(*, client: TestClient, db_session: Session) -> None:
    """Check a non-member can query a project the owner made public."""

    alice_headers, project_id = _create_project(client=client, email="alice-pub@example.com")
    seed_document_with_chunks(
        db=db_session, project_id=UUID(project_id), chunk_texts=["alpha"], filename="pub.pdf"
    )
    made_public = client.patch(f"/api/projects/{project_id}", json={"is_public": True}, headers=alice_headers)
    assert made_public.status_code == 200
    bob_headers = _auth(client=client, email="bob-pub@example.com")
    response = client.post(
        f"/api/projects/{project_id}/retrieve", json={"query": "alpha"}, headers=bob_headers
    )
    assert response.status_code == 200
    assert [item["text"] for item in response.json()] == ["alpha"]


@pytest.mark.parametrize(
    "body",
    [
        {"query": "   "},
        {"query": "x" * 2001},
        {"query": "\u0000x"},
        {"query": "x", "top_k": 0},
        {"query": "x", "top_k": 51},
        {"query": "x", "max_chunks_per_document": 0},
    ],
)
def test_retrieve_validation_errors(*, client: TestClient, body: dict[str, object]) -> None:
    """Check malformed bodies answer 422."""

    headers, project_id = _create_project(client=client, email=f"val-{uuid4()}@example.com")
    response = client.post(f"/api/projects/{project_id}/retrieve", json=body, headers=headers)
    assert response.status_code == 422


def test_retrieve_strips_and_matches(*, client: TestClient, db_session: Session) -> None:
    """Check a padded query strips and still matches its chunk."""

    headers, project_id = _create_project(client=client, email="strip@example.com")
    seed_document_with_chunks(db=db_session, project_id=UUID(project_id), chunk_texts=["alpha alpha"])
    response = client.post(
        f"/api/projects/{project_id}/retrieve", json={"query": "  alpha  "}, headers=headers
    )
    assert response.status_code == 200
    assert [item["text"] for item in response.json()] == ["alpha alpha"]


def test_rerank_true_accepted_and_ignored(*, client: TestClient, db_session: Session) -> None:
    """Check the rerank flag is accepted and changes nothing until the S6 reranker."""

    headers, project_id = _create_project(client=client, email="rerank@example.com")
    seed_document_with_chunks(
        db=db_session, project_id=UUID(project_id), chunk_texts=["alpha", "bravo alpha"]
    )
    without = client.post(
        f"/api/projects/{project_id}/retrieve", json={"query": "alpha"}, headers=headers
    ).json()
    with_flag = client.post(
        f"/api/projects/{project_id}/retrieve",
        json={"query": "alpha", "rerank": True},
        headers=headers,
    ).json()
    assert with_flag == without


def test_retrieve_empty_project_returns_empty_list(*, client: TestClient, db_session: Session) -> None:
    """Check a project with no indexed chunks answers an empty list and still logs."""

    headers, project_id = _create_project(client=client, email="empty-api@example.com")
    response = client.post(f"/api/projects/{project_id}/retrieve", json={"query": "alpha"}, headers=headers)
    assert response.status_code == 200
    assert response.json() == []
    log = db_session.scalars(select(QueryLog).where(QueryLog.project_id == UUID(project_id))).one()
    assert log.stages["final"] == []


def test_retrieve_response_shape(*, client: TestClient, db_session: Session) -> None:
    """Check the response items carry exactly the served fields."""

    headers, project_id = _create_project(client=client, email="shape@example.com")
    seeded = seed_document_with_chunks(
        db=db_session,
        project_id=UUID(project_id),
        chunk_texts=["alpha alpha"],
        filename="shape.pdf",
    )
    response = client.post(
        f"/api/projects/{project_id}/retrieve",
        json={"query": "alpha", "top_k": 5},
        headers=headers,
    )
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    item = items[0]
    assert set(item) == {
        "id",
        "document_id",
        "source_item_id",
        "filename",
        "position",
        "heading_path",
        "chunk_type",
        "text",
        "score",
    }
    assert item["id"] == str(seeded.chunk_ids[0])
    assert item["document_id"] == str(seeded.document_id)
    assert item["source_item_id"] == str(seeded.source_item_id)
    assert item["filename"] == "shape.pdf"
    assert item["position"] == 0
    assert item["heading_path"] == []
    assert item["chunk_type"] == "text"
    assert item["text"] == "alpha alpha"
    assert isinstance(item["score"], float)


def test_length_limit_applies_after_strip(*, client: TestClient) -> None:
    """Check the character cap counts the stripped query, not the padded one."""

    headers, project_id = _create_project(client=client, email="strip-len@example.com")
    response = client.post(
        f"/api/projects/{project_id}/retrieve",
        json={"query": "x" * 1999 + "  "},
        headers=headers,
    )
    assert response.status_code == 200


def test_top_k_defaults_and_limits(*, client: TestClient, db_session: Session) -> None:
    """Check the default top_k caps the answer at ten of twelve chunks."""

    headers, project_id = _create_project(client=client, email="topk@example.com")
    seed_document_with_chunks(
        db=db_session,
        project_id=UUID(project_id),
        chunk_texts=[f"alpha {i}" for i in range(12)],
    )
    response = client.post(f"/api/projects/{project_id}/retrieve", json={"query": "alpha"}, headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 10
