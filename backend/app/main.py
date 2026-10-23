"""FastAPI application assembly."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Aliased because the FastAPI instance below is also named app; the import still
# registers every ORM model.
import app.models as app_models  # noqa: F401
from app.answers.router import router as answers_router
from app.conversations.router import router as conversations_router
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.identity.router import router as identity_router
from app.ingestion.schema_guard import run_startup_checks
from app.projects.router import router as projects_router
from app.providers import get_embedding_provider
from app.retrieval.router import router as retrieval_router
from app.sources.router import router as sources_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Run the startup checks once per process, before the app serves anything."""

    # The module-level SessionLocal indirection keeps the factory swappable for
    # tests; a direct import binding could not be redirected.
    session = SessionLocal()
    try:
        run_startup_checks(db=session, embedding_provider=get_embedding_provider(settings=get_settings()))
    finally:
        session.close()
    yield


app = FastAPI(
    title="rag-mvp",
    docs_url="/api/docs",
    swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.include_router(identity_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(sources_router, prefix="/api")
app.include_router(retrieval_router, prefix="/api")
app.include_router(answers_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")

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
