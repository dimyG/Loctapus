import uuid


def _register(client, email="me@example.com"):
    r = client.post("/auth/register",
                    json={"email": email, "password": "password123"})
    return r.json()["access_token"]


def test_users_me_returns_ids(client):
    token = _register(client)
    r = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "me@example.com"
    uuid.UUID(body["user_id"]); uuid.UUID(body["workspace_id"]); uuid.UUID(body["team_id"])


def test_users_me_requires_auth(client):
    assert client.get("/users/me").status_code in (401, 403)


def test_users_me_rejects_bad_token(client):
    r = client.get("/users/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid or expired token"}


def test_users_me_expired_token_401(client, settings):
    from datetime import datetime, timedelta, timezone
    import jwt as pyjwt

    token = pyjwt.encode(
        {"sub": str(uuid.uuid4()),
         "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        settings.jwt_secret, algorithm=settings.jwt_algorithm)
    r = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid or expired token"}
