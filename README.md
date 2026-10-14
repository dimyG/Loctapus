# RAG MVP

FastAPI + SQLAlchemy 2.0 + pgvector backend for a RAG MVP, sliced into incremental
deliverables. Identity (users, workspaces, teams) and projects are done; document
ingestion and retrieval build on top in later slices.

## Prerequisites

- Python 3.14
- Docker (for Postgres/pgvector, RabbitMQ, and Garage)

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

This starts Postgres (pgvector, `localhost:5432`, `rag`/`rag`), RabbitMQ (management
UI on `localhost:15672`), and Garage (S3 API on `localhost:3900`, admin on
`localhost:3903`, `rag-dev-key`/`rag-dev-secret-local`, bucket `rag-dev`). Garage
provisions its default key and bucket on first start, so there is no bootstrap step.

Do not change `GARAGE_DEFAULT_SECRET_KEY` after first start: Garage binds its stored
layout to the secret it was created with, startup fails with a different one, and the
metadata volume must be wiped to recover.

RabbitMQ state lives on the named `rabbitmqdata` volume, so queues and vhosts survive a
`docker compose up -d --force-recreate rabbitmq`. This volume was introduced after the
broker had run without one: recreating the container discards that old anonymous volume
once, and the `rag_test` and `rag_e2e` vhosts are recreated by their suites' bootstraps.

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

## Run the ingestion workers

Uploads are processed by a Celery worker and a standalone outbox dispatcher, both
started from `backend/` with the venv:

```powershell
cd backend
..\.venv\Scripts\celery -A app.workers.celery_app worker --pool=solo -Q ingestion,embed
```

```powershell
cd backend
..\.venv\Scripts\python -m app.workers.dispatcher
```

The worker consumes the `ingestion` and `embed` queues; `--pool=solo` is the
supported Windows pool (prefork is unsupported on Windows). The dispatcher polls
the transactional outbox and publishes pending events to RabbitMQ. An upload stays
`queued` until both processes are running.

## Test

Tests need the compose services up: the real Postgres for every suite (never
SQLite), plus RabbitMQ and Garage for the outbox/worker integration tests. The
`engine` fixture creates a disposable `rag_test` database, applies all migrations,
and drops it after the session; the `rag_test` broker vhost is created by the suite
itself, so no manual broker setup is needed.

```powershell
cd backend
..\.venv\Scripts\python -m pytest
```

Before finishing a change, `ruff check .` and `mypy app tests` must also pass
(see `AGENTS.md`).

## Line endings

`.gitattributes` pins every text file to LF (the web toolchain's prettier
enforces LF). Clones made before that file exist need a one-time refresh -
`git add --renormalize .` - or `prettier --check .` fails on identical
committed content with CRLF working copies.

## Further reading

- Slice design: `docs/superpowers/specs/2026-10-06-rag-mvp-slices-design.md`
- Follow-ups and deferred findings: `docs/superpowers/backlog.md`