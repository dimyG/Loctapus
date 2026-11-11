"""End-to-end smoke test for the full happy path."""

import pytest
from fastapi.testclient import TestClient

# The test drives the full API happy path through the assembled app, so it belongs to the long bucket.
pytestmark = pytest.mark.long


def test_register_login_project_lifecycle(*, client: TestClient) -> None:
    """Check that register, login, project create, fetch, and delete all work through the API.

    :param client: TestClient wired to the assembled application.
    """

    token = client.post(
        "/api/auth/register",
        json={"email": "e2e@example.com", "password": "password123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    ws = client.get("/api/workspaces", headers=headers).json()[0]
    team_id = client.get(f"/api/workspaces/{ws['id']}/teams", headers=headers).json()[0]["id"]

    token2 = client.post(
        "/api/auth/login",
        json={"email": "e2e@example.com", "password": "password123"},
    ).json()["access_token"]
    assert token2

    me = client.get("/api/users/me", headers=headers).json()
    assert me["email"] == "e2e@example.com"

    created = client.post("/api/projects", json={"name": "e2e-kb", "team_id": team_id}, headers=headers)
    pid = created.json()["id"]
    assert client.get(f"/api/projects/{pid}", headers=headers).status_code == 200
    names = [p["name"] for p in client.get("/api/projects", headers=headers).json()]
    assert sorted(names) == ["Default", "e2e-kb"]
    assert client.delete(f"/api/projects/{pid}", headers=headers).status_code == 204
    assert [p["name"] for p in client.get("/api/projects", headers=headers).json()] == ["Default"]
