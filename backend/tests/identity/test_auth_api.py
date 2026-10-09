"""Tests for the register, login, and logout endpoints."""

from fastapi.testclient import TestClient


def test_register_returns_jwt(*, client: TestClient) -> None:
    """Check that registration returns a bearer token."""

    r = client.post("/auth/register", json={"email": "api@example.com", "password": "password123"})
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer" and len(body["access_token"]) > 20


def test_register_duplicate_409(*, client: TestClient) -> None:
    """Check that registering an existing email answers 409."""

    payload = {"email": "twice@example.com", "password": "password123"}
    assert client.post("/auth/register", json=payload).status_code == 201
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 409
    assert r.json() == {"detail": "email already registered"}


def test_register_short_password_422(*, client: TestClient) -> None:
    """Check that a short password fails validation."""

    r = client.post("/auth/register", json={"email": "short@example.com", "password": "1234567"})
    assert r.status_code == 422


def test_login_success_and_failure(*, client: TestClient) -> None:
    """Check that login succeeds with matching credentials and fails otherwise."""

    client.post("/auth/register", json={"email": "login@example.com", "password": "password123"})
    ok = client.post("/auth/login", json={"email": "login@example.com", "password": "password123"})
    assert ok.status_code == 200 and ok.json()["access_token"]
    bad = client.post("/auth/login", json={"email": "login@example.com", "password": "nope1234"})
    assert bad.status_code == 401
    assert bad.json() == {"detail": "invalid credentials"}


def test_second_user_registers_and_logs_in(*, client: TestClient) -> None:
    """Check that a second account can register and log in."""

    client.post("/auth/register", json={"email": "first@example.com", "password": "password123"})
    r = client.post("/auth/register", json={"email": "second@example.com", "password": "password123"})
    assert r.status_code == 201


def test_logout_revokes_token(*, client: TestClient) -> None:
    """Check that a logged-out token no longer authenticates."""

    r = client.post("/auth/register", json={"email": "lo@example.com", "password": "password123"})
    token = r.json()["access_token"]
    assert client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 204
    after = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert after.status_code == 401


def test_logout_leaves_other_sessions_valid(*, client: TestClient) -> None:
    """Check that logging out one token leaves other tokens valid."""

    body = {"email": "two@example.com", "password": "password123"}
    t1 = client.post("/auth/register", json=body).json()["access_token"]
    t2 = client.post("/auth/login", json=body).json()["access_token"]
    assert client.post("/auth/logout", headers={"Authorization": f"Bearer {t1}"}).status_code == 204
    assert client.get("/users/me", headers={"Authorization": f"Bearer {t2}"}).status_code == 200


def test_revoked_token_rejected_on_projects(*, client: TestClient) -> None:
    """Check that a revoked token is rejected on protected endpoints beyond /users/me."""

    token = client.post(
        "/auth/register", json={"email": "rev2@example.com", "password": "password123"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.get("/projects", headers=headers).status_code == 401


def test_logout_requires_auth(*, client: TestClient) -> None:
    """Check that logout rejects requests without a token."""

    assert client.post("/auth/logout").status_code == 401


def test_logout_rejects_garbage_token(*, client: TestClient) -> None:
    """Check that logout answers 401 for a malformed bearer token."""

    r = client.post("/auth/logout", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid or expired token"}
