def _auth(client, email):
    r = client.post("/auth/register",
                    json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _default_team_id(client, headers):
    ws = client.get("/workspaces", headers=headers).json()[0]
    return client.get(f"/workspaces/{ws['id']}/teams", headers=headers).json()[0]["id"]


def test_create_and_list_projects(client):
    headers = _auth(client, "crl@example.com")
    team_id = _default_team_id(client, headers)
    r = client.post("/projects", json={"name": "kb", "team_id": team_id}, headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "kb" and body["id"] and body["created_at"]
    listed = client.get("/projects", headers=headers)
    assert listed.status_code == 200
    assert sorted(p["name"] for p in listed.json()) == ["Default", "kb"]


def test_get_other_users_project_is_404(client):
    alice = _auth(client, "a2@example.com")
    bob = _auth(client, "b2@example.com")
    team_id = _default_team_id(client, alice)
    pid = client.post("/projects", json={"name": "secret", "team_id": team_id},
                      headers=alice).json()["id"]
    r = client.get(f"/projects/{pid}", headers=bob)
    assert r.status_code == 404
    assert r.json() == {"detail": "project not found"}


def test_projects_require_auth(client):
    assert client.get("/projects").status_code in (401, 403)
    assert client.post("/projects", json={"name": "x"}).status_code in (401, 403)


def test_create_project_validates_name(client):
    headers = _auth(client, "val@example.com")
    team_id = _default_team_id(client, headers)
    r = client.post("/projects", json={"name": "", "team_id": team_id}, headers=headers)
    assert r.status_code == 422


def test_create_project_rejects_foreign_team(client):
    alice = _auth(client, "fa@example.com")
    bob = _auth(client, "fb@example.com")
    bob_team_id = _default_team_id(client, bob)
    r = client.post("/projects", json={"name": "x", "team_id": bob_team_id}, headers=alice)
    assert r.status_code == 404


def test_delete_project_flow_and_cross_user_404(client):
    alice = _auth(client, "del-a@example.com")
    bob = _auth(client, "del-b@example.com")
    team_id = _default_team_id(client, alice)
    pid = client.post("/projects", json={"name": "temp", "team_id": team_id},
                      headers=alice).json()["id"]
    assert client.delete(f"/projects/{pid}", headers=bob).status_code == 404
    assert client.delete(f"/projects/{pid}", headers=alice).status_code == 204
    assert client.get(f"/projects/{pid}", headers=alice).status_code == 404
    assert client.delete(f"/projects/{pid}", headers=alice).status_code == 404
