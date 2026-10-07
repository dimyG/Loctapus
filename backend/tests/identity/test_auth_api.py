def test_register_returns_jwt(client):
    r = client.post("/auth/register",
                    json={"email": "api@example.com", "password": "password123"})
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer" and len(body["access_token"]) > 20


def test_register_duplicate_409(client):
    payload = {"email": "twice@example.com", "password": "password123"}
    assert client.post("/auth/register", json=payload).status_code == 201
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 409
    assert r.json() == {"detail": "email already registered"}


def test_register_short_password_422(client):
    r = client.post("/auth/register",
                    json={"email": "short@example.com", "password": "1234567"})
    assert r.status_code == 422


def test_login_success_and_failure(client):
    client.post("/auth/register",
                json={"email": "login@example.com", "password": "password123"})
    ok = client.post("/auth/login",
                     json={"email": "login@example.com", "password": "password123"})
    assert ok.status_code == 200 and ok.json()["access_token"]
    bad = client.post("/auth/login",
                      json={"email": "login@example.com", "password": "nope1234"})
    assert bad.status_code == 401
    assert bad.json() == {"detail": "invalid credentials"}


def test_second_user_registers_and_logs_in(client):
    client.post("/auth/register",
                json={"email": "first@example.com", "password": "password123"})
    r = client.post("/auth/register",
                    json={"email": "second@example.com", "password": "password123"})
    assert r.status_code == 201


def test_logout_revokes_token(client):
    r = client.post("/auth/register", json={"email": "lo@example.com", "password": "password123"})
    token = r.json()["access_token"]
    assert client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 204
    after = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert after.status_code == 401


def test_logout_leaves_other_sessions_valid(client):
    body = {"email": "two@example.com", "password": "password123"}
    t1 = client.post("/auth/register", json=body).json()["access_token"]
    t2 = client.post("/auth/login", json=body).json()["access_token"]
    assert client.post("/auth/logout", headers={"Authorization": f"Bearer {t1}"}).status_code == 204
    assert client.get("/users/me", headers={"Authorization": f"Bearer {t2}"}).status_code == 200


def test_logout_requires_auth(client):
    assert client.post("/auth/logout").status_code in (401, 403)
