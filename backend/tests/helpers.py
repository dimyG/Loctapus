"""Shared test helpers."""

from fastapi.testclient import TestClient
from pydantic_settings import SettingsConfigDict

from app.core.config import Settings


class SettingsForTests(Settings):
    """Settings subclass for tests, identical to Settings but it never reads a .env file."""

    model_config = SettingsConfigDict(env_file=None)


def _auth(*, client: TestClient, email: str) -> dict[str, str]:
    """Register an account and return its bearer headers.

    :param client: TestClient wired to the app.
    :param email: Address to register the account with.
    """

    response = client.post("/api/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _default_team_id(*, client: TestClient, headers: dict[str, str]) -> str:
    """Return the account's default team id through the API.

    :param client: TestClient wired to the app.
    :param headers: Bearer headers identifying the account to look up.
    """

    workspace = client.get("/api/workspaces", headers=headers).json()[0]
    return str(client.get(f"/api/workspaces/{workspace['id']}/teams", headers=headers).json()[0]["id"])
