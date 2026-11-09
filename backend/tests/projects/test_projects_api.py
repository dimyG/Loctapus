"""Tests for the project HTTP endpoints."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _auth(*, client: TestClient, email: str) -> dict[str, str]:
    """Register an account and return its bearer headers.

    :param client: TestClient wired to the app with the rollback-managed session.
    :param email: Address to register.
    """

    r = client.post("/api/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _default_team_id(*, client: TestClient, headers: dict[str, str]) -> str:
    """Return the account's default team id through the API.

    :param client: TestClient wired to the app with the rollback-managed session.
    :param headers: Bearer headers of the account whose team is looked up.
    """

    ws = client.get("/api/workspaces", headers=headers).json()[0]
    return str(client.get(f"/api/workspaces/{ws['id']}/teams", headers=headers).json()[0]["id"])


def test_create_and_list_projects(*, client: TestClient) -> None:
    """Check that a created project is listed beside the account's default project.

    :param client: TestClient wired to the app with the rollback-managed session.
    """

    headers = _auth(client=client, email="crl@example.com")
    team_id = _default_team_id(client=client, headers=headers)
    r = client.post("/api/projects", json={"name": "kb", "team_id": team_id}, headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "kb" and body["id"] and body["created_at"]
    listed = client.get("/api/projects", headers=headers)
    assert listed.status_code == 200
    assert sorted(p["name"] for p in listed.json()) == ["Default", "kb"]


def test_get_project_not_shared_with_user_is_404(*, client: TestClient) -> None:
    """Check that a stranger cannot fetch a private project.

    :param client: TestClient wired to the app with the rollback-managed session.
    """

    alice = _auth(client=client, email="a2@example.com")
    bob = _auth(client=client, email="b2@example.com")
    team_id = _default_team_id(client=client, headers=alice)
    created = client.post("/api/projects", json={"name": "secret", "team_id": team_id}, headers=alice)
    pid = created.json()["id"]
    r = client.get(f"/api/projects/{pid}", headers=bob)
    assert r.status_code == 404
    assert r.json() == {"detail": "project not found"}


def test_projects_require_auth(*, client: TestClient) -> None:
    """Check that the project endpoints reject unauthenticated requests.

    :param client: TestClient wired to the app with the rollback-managed session.
    """

    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/projects", json={"name": "x"}).status_code == 401


def test_create_project_validates_name(*, client: TestClient) -> None:
    """Check that an empty name fails validation.

    :param client: TestClient wired to the app with the rollback-managed session.
    """

    headers = _auth(client=client, email="val@example.com")
    team_id = _default_team_id(client=client, headers=headers)
    r = client.post("/api/projects", json={"name": "", "team_id": team_id}, headers=headers)
    assert r.status_code == 422


def test_create_project_requires_team_membership(*, client: TestClient) -> None:
    """Check that creating on a stranger's team answers 404.

    :param client: TestClient wired to the app with the rollback-managed session.
    """

    alice = _auth(client=client, email="fa@example.com")
    bob = _auth(client=client, email="fb@example.com")
    bob_team_id = _default_team_id(client=client, headers=bob)
    r = client.post("/api/projects", json={"name": "x", "team_id": bob_team_id}, headers=alice)
    assert r.status_code == 404


def test_delete_project_flow_and_cross_user_404(*, client: TestClient) -> None:
    """Check that only the owning admin can delete, and that a deleted project stays 404.

    :param client: TestClient wired to the app with the rollback-managed session.
    """

    alice = _auth(client=client, email="del-a@example.com")
    bob = _auth(client=client, email="del-b@example.com")
    team_id = _default_team_id(client=client, headers=alice)
    pid = client.post("/api/projects", json={"name": "temp", "team_id": team_id}, headers=alice).json()["id"]
    assert client.delete(f"/api/projects/{pid}", headers=bob).status_code == 404
    assert client.delete(f"/api/projects/{pid}", headers=alice).status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=alice).status_code == 404
    assert client.delete(f"/api/projects/{pid}", headers=alice).status_code == 404


def test_public_project_visible_to_non_member(*, client: TestClient) -> None:
    """Check that a public project is readable and listed for strangers.

    :param client: TestClient wired to the app with the rollback-managed session.
    """

    alice = _auth(client=client, email="pa@example.com")
    bob = _auth(client=client, email="pb@example.com")
    pid = client.post(
        "/api/projects",
        json={"name": "pub", "team_id": _default_team_id(client=client, headers=alice)},
        headers=alice,
    ).json()["id"]
    made_public = client.patch(f"/api/projects/{pid}", json={"is_public": True}, headers=alice)
    assert made_public.status_code == 200 and made_public.json()["is_public"] is True
    assert client.get(f"/api/projects/{pid}", headers=bob).status_code == 200
    assert any(p["id"] == pid for p in client.get("/api/projects/public", headers=bob).json())
    assert [p["name"] for p in client.get("/api/projects", headers=bob).json()] == ["Default"]


def test_public_project_not_editable_by_non_member(*, client: TestClient) -> None:
    """Check that a stranger with view access cannot modify or delete.

    :param client: TestClient wired to the app with the rollback-managed session.
    """

    alice = _auth(client=client, email="qa@example.com")
    bob = _auth(client=client, email="qb@example.com")
    pid = client.post(
        "/api/projects",
        json={"name": "pub2", "team_id": _default_team_id(client=client, headers=alice)},
        headers=alice,
    ).json()["id"]
    made_public = client.patch(f"/api/projects/{pid}", json={"is_public": True}, headers=alice)
    assert made_public.status_code == 200 and made_public.json()["is_public"] is True
    # Public visibility grants read access only; writes still require an admin role.
    assert client.get(f"/api/projects/{pid}", headers=bob).status_code == 200
    assert client.patch(f"/api/projects/{pid}", json={"name": "hax"}, headers=bob).status_code == 404
    assert client.delete(f"/api/projects/{pid}", headers=bob).status_code == 404
    # The failed patch left the stored name unchanged.
    assert client.get(f"/api/projects/{pid}", headers=bob).json()["name"] == "pub2"


def test_patch_updates_name_and_visibility(*, client: TestClient) -> None:
    """Check that a patch updates name and visibility together.

    :param client: TestClient wired to the app with the rollback-managed session.
    """

    h = _auth(client=client, email="pu@example.com")
    pid = client.post(
        "/api/projects",
        json={"name": "old", "team_id": _default_team_id(client=client, headers=h)},
        headers=h,
    ).json()["id"]
    r = client.patch(f"/api/projects/{pid}", json={"name": "new", "is_public": True}, headers=h)
    assert r.status_code == 200 and r.json()["name"] == "new" and r.json()["is_public"] is True


def test_patch_rejects_explicit_nulls(*, client: TestClient) -> None:
    """Check that an explicit null in a patch body is rejected instead of ignored.

    :param client: TestClient wired to the app with the rollback-managed session.
    """

    h = _auth(client=client, email="null@example.com")
    pid = client.post(
        "/api/projects",
        json={"name": "nulled", "team_id": _default_team_id(client=client, headers=h)},
        headers=h,
    ).json()["id"]
    assert client.patch(f"/api/projects/{pid}", json={"name": None}, headers=h).status_code == 422
    assert client.patch(f"/api/projects/{pid}", json={"is_public": None}, headers=h).status_code == 422
    assert client.get(f"/api/projects/{pid}", headers=h).json()["name"] == "nulled"


def test_patch_rejects_non_admin_team_member(*, client: TestClient, db_session: Session) -> None:
    """Check that a viewer-role team member cannot patch.

    :param client: TestClient wired to the app with the rollback-managed session.
    :param db_session: Session used to insert the viewer role directly.
    """

    from app.projects.models import ProjectTeamRole

    alice = _auth(client=client, email="role-a@example.com")
    viewer_headers = _auth(client=client, email="role-v@example.com")
    pid = client.post(
        "/api/projects",
        json={"name": "roled", "team_id": _default_team_id(client=client, headers=alice)},
        headers=alice,
    ).json()["id"]
    # The viewer's own team holds only a viewer (non-admin) role on the project.
    viewer_team_id = _default_team_id(client=client, headers=viewer_headers)
    db_session.add(
        ProjectTeamRole(project_id=uuid.UUID(pid), team_id=uuid.UUID(viewer_team_id), role="viewer")
    )
    db_session.flush()
    r = client.patch(f"/api/projects/{pid}", json={"name": "hax"}, headers=viewer_headers)
    assert r.status_code == 404
