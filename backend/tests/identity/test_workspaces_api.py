def _auth(client, email):
    r = client.post("/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_list_workspaces_and_teams(client):
    headers = _auth(client, "ws@example.com")
    ws = client.get("/workspaces", headers=headers).json()
    assert len(ws) == 1 and ws[0]["name"] == "Default"
    teams = client.get(f"/workspaces/{ws[0]['id']}/teams", headers=headers).json()
    assert len(teams) == 1 and teams[0]["name"] == "Default" and teams[0]["workspace_id"] == ws[0]["id"]


def test_workspace_teams_unknown_workspace_404(client):
    headers = _auth(client, "ws2@example.com")
    r = client.get("/workspaces/00000000-0000-0000-0000-000000000000/teams", headers=headers)
    assert r.status_code == 404
    assert r.json() == {"detail": "workspace not found"}


def test_workspaces_require_auth(client):
    assert client.get("/workspaces").status_code in (401, 403)
