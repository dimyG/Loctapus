"""FastAPI application assembly."""

from fastapi import FastAPI

from app.identity.router import router as identity_router
from app.projects.router import router as projects_router

app = FastAPI(title="rag-mvp")
app.include_router(identity_router)
app.include_router(projects_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Report service liveness."""

    return {"status": "ok"}
