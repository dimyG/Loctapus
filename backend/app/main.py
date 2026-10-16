"""FastAPI application assembly."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Aliased because the FastAPI instance below is also named app; the import still
# registers every ORM model.
import app.models as app_models  # noqa: F401
from app.core.config import get_settings
from app.identity.router import router as identity_router
from app.projects.router import router as projects_router
from app.sources.router import router as sources_router

app = FastAPI(
    title="rag-mvp",
    docs_url="/api/docs",
    swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.include_router(identity_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(sources_router, prefix="/api")

# SPA origins are explicit (no wildcard) so browsers reject cross-site reads from
# unknown hosts; auth is a Bearer header, so cookies never cross origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Report service liveness."""

    return {"status": "ok"}
