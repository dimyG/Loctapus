"""Tests for the workspace and team listing endpoints."""

from fastapi.testclient import TestClient


def _auth(*, client: TestClient, email: str) -> dict[str, str]:
    """Register an account and return its bearer headers."""

    r = client.post("/api/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_list_workspaces_and_teams(*, client: TestClient) -> None:
    """Check that a fresh account lists one default workspace and team."""

    headers = _auth(client=client, email="ws@example.com")
    ws = client.get("/api/workspaces", headers=headers).json()
    assert len(ws) == 1 and ws[0]["name"] == "Default"
    teams = client.get(f"/api/workspaces/{ws[0]['id']}/teams", headers=headers).json()
    assert len(teams) == 1 and teams[0]["name"] == "Default" and teams[0]["workspace_id"] == ws[0]["id"]


def test_workspace_teams_unknown_workspace_404(*, client: TestClient) -> None:
    """Check that teams in an unknown workspace answer 404."""

    headers = _auth(client=client, email="ws2@example.com")
    r = client.get("/api/workspaces/00000000-0000-0000-0000-000000000000/teams", headers=headers)
    assert r.status_code == 404
    assert r.json() == {"detail": "workspace not found"}


def test_workspaces_require_auth(*, client: TestClient) -> None:
    """Check that the workspace endpoints reject unauthenticated requests."""

    assert client.get("/api/workspaces").status_code == 401
