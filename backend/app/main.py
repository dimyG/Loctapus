from fastapi import FastAPI

app = FastAPI(title="rag-mvp")


@app.get("/health")
def health():
    return {"status": "ok"}
