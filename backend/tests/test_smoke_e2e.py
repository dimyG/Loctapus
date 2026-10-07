def test_register_login_project_lifecycle(client):
    token = client.post(
        "/auth/register",
        json={"email": "e2e@example.com", "password": "password123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    ws = client.get("/workspaces", headers=headers).json()[0]
    team_id = client.get(f"/workspaces/{ws['id']}/teams", headers=headers).json()[0]["id"]

    token2 = client.post(
        "/auth/login",
        json={"email": "e2e@example.com", "password": "password123"},
    ).json()["access_token"]
    assert token2

    me = client.get("/users/me", headers=headers).json()
    assert me["email"] == "e2e@example.com"

    pid = client.post("/projects", json={"name": "e2e-kb", "team_id": team_id},
                      headers=headers).json()["id"]
    assert client.get(f"/projects/{pid}", headers=headers).status_code == 200
    names = [p["name"] for p in client.get("/projects", headers=headers).json()]
    assert sorted(names) == ["Default", "e2e-kb"]
    assert client.delete(f"/projects/{pid}", headers=headers).status_code == 204
    assert [p["name"] for p in client.get("/projects", headers=headers).json()] == ["Default"]
