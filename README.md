# RAG MVP

FastAPI + SQLAlchemy 2.0 + pgvector backend for a RAG MVP, sliced into incremental
deliverables. Identity (users, workspaces, teams) and projects are done; document
ingestion and retrieval build on top in later slices.

## Prerequisites

- Python 3.14
- Docker (for Postgres/pgvector, RabbitMQ, and MinIO)

## Setup

```powershell
python -m venv .venv
.venv\Scripts\pip install -e "backend[dev]"
```

Configuration comes from `RAG_`-prefixed environment variables (see
`backend/app/core/config.py`), with a `.env` file supported in `backend/`.
The defaults target the compose services below.

## Run the services

```powershell
docker compose -f deploy/docker-compose.yml up -d
```

This starts Postgres (pgvector, `localhost:5432`, `rag`/`rag`),
RabbitMQ (management UI on `localhost:15672`), and MinIO (console on `localhost:9001`,
`minio`/`minio123`). MinIO's community edition is end-of-life; see the TODO in
`deploy/docker-compose.yml` about replacing it.

## Migrate the development database

```powershell
cd backend
..\.venv\Scripts\alembic upgrade head
```

## Run the API

```powershell
cd backend
..\.venv\Scripts\uvicorn app.main:app --reload
```

The API serves `http://localhost:8000`; `/docs` lists the endpoints.

## Test

Tests run against the real Postgres from compose (never SQLite). The `engine`
fixture creates a disposable `rag_test` database, applies all migrations, and drops
it after the session.

```powershell
cd backend
..\.venv\Scripts\python -m pytest
```

Before finishing a change, `ruff check .` and `mypy app tests` must also pass
(see `AGENTS.md`).

## Further reading

- Slice design: `docs/superpowers/specs/2026-10-06-rag-mvp-slices-design.md`
- Follow-ups and deferred findings: `docs/superpowers/backlog.md`