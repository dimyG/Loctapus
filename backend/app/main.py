from fastapi import FastAPI

from app.identity.router import router as identity_router

app = FastAPI(title="rag-mvp")
app.include_router(identity_router)


@app.get("/health")
def health():
    return {"status": "ok"}
