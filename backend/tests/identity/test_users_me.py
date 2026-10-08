"""Tests for the /users/me endpoint."""

import uuid
from datetime import UTC

from fastapi.testclient import TestClient


def _register(*, client: TestClient, email: str = "me@example.com") -> str:
    """Register an account and return its access token."""

    r = client.post("/auth/register", json={"email": email, "password": "password123"})
    return str(r.json()["access_token"])


def test_users_me_returns_ids(*, client: TestClient) -> None:
    """Check that /users/me returns the user id and email."""

    token = _register(client=client)
    r = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "me@example.com"
    uuid.UUID(body["user_id"])
    assert "workspace_id" not in body and "team_id" not in body


def test_users_me_requires_auth(*, client: TestClient) -> None:
    """Check that /users/me rejects requests without a token."""

    assert client.get("/users/me").status_code in (401, 403)


def test_users_me_rejects_bad_token(*, client: TestClient) -> None:
    """Check that /users/me rejects a malformed bearer token."""

    r = client.get("/users/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid or expired token"}


def test_users_me_expired_token_401(*, client: TestClient) -> None:
    """Check that /users/me rejects an otherwise-valid token once it expires."""

    from datetime import datetime, timedelta

    import jwt as pyjwt

    from app.core.config import get_settings

    # The TestClient app verifies with the process settings, so resign with those.
    app_settings = get_settings()
    token = _register(client=client, email="expired@example.com")
    # Control: the fresh token itself is accepted, so the rejection below can only be the expiry.
    assert client.get("/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    claims = pyjwt.decode(token, app_settings.jwt_secret, algorithms=[app_settings.jwt_algorithm])
    claims["exp"] = datetime.now(UTC) - timedelta(hours=1)
    expired = pyjwt.encode(claims, app_settings.jwt_secret, algorithm=app_settings.jwt_algorithm)
    r = client.get("/users/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid or expired token"}
