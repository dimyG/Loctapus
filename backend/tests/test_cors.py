"""Tests for CORS preflight and echo behavior of the assembled application."""

from fastapi.testclient import TestClient


def test_preflight_allows_dev_origin(*, client: TestClient) -> None:
    """Check that a preflight from the Vite origin is answered with the echoed ACAO header.

    :param client: TestClient wired to the assembled application.
    """

    response = client.options(
        "/api/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_preflight_rejects_unknown_origin(*, client: TestClient) -> None:
    """Check that a preflight from an origin outside the list gets no ACAO header.

    :param client: TestClient wired to the assembled application.
    """

    response = client.options(
        "/api/health",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_get_echoes_allowed_origin(*, client: TestClient) -> None:
    """Check that a simple GET from an allowed origin carries the ACAO header.

    :param client: TestClient wired to the assembled application.
    """

    response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
