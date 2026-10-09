"""FastAPI application assembly."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.identity.router import router as identity_router
from app.projects.router import router as projects_router

app = FastAPI(title="rag-mvp")
app.include_router(identity_router)
app.include_router(projects_router)

# SPA origins are explicit (no wildcard) so browsers reject cross-site reads from
# unknown hosts; auth is a Bearer header, so cookies never cross origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Report service liveness."""

    return {"status": "ok"}
