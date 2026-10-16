"""The API surface lives entirely under the /api prefix."""

from starlette.routing import Route

from app.main import app


def test_every_route_is_under_api() -> None:
    """Check that no route (docs surfaces included) escapes the /api prefix nginx forwards."""

    # Included routers are not plain Route entries on newer FastAPI, so their paths come from the schema.
    paths = [route.path for route in app.routes if isinstance(route, Route)]
    paths += list(app.openapi()["paths"])
    assert paths, "no routes found on the assembled app"
    assert all(path.startswith("/api/") for path in paths), sorted(paths)
