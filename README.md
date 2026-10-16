# RAG MVP

FastAPI + SQLAlchemy 2.0 + pgvector backend for a RAG MVP, sliced into incremental
deliverables. Identity (users, workspaces, teams), projects, and the upload+ingestion
pipeline (upload -> parse -> chunk -> embed) are done; retrieval builds on top in later
slices.

## Prerequisites

- Python 3.14
- Node.js (for the web toolchain and e2e)
- Docker (runs the whole system: Postgres/pgvector, RabbitMQ, Garage, and the app tier)

## Setup

```powershell
python -m venv .venv
.venv\Scripts\pip install -e "backend[dev]"
npm install --prefix web
```

The venv serves the test suites and migrations authoring, not the running system.
`npm install` serves the web toolchain (tests, lint, format) and the e2e suite.

Configuration comes from `RAG_`-prefixed environment variables (see
`backend/app/core/config.py`), with a `.env` file supported in `backend/`.
The defaults target the compose services below, as seen from the host (the test
suites); the containers get their own addresses from the compose file.

## Run the whole system

```powershell
docker compose -f deploy/docker-compose.yml up -d
```

This builds and starts all eight services: Postgres (pgvector, `localhost:5432`,
`rag`/`rag`), RabbitMQ (management UI on `localhost:15672`), Garage (S3 API on
`localhost:3900`, admin on `localhost:3903`, `rag-dev-key`/`rag-dev-secret-local`,
bucket `rag-dev`), the one-off initialization step that migrates the schema, and the
API, the Celery worker, the outbox dispatcher, and the web UI. No manual steps are
needed: the migration runs before the app services start, and Garage provisions its
default key and bucket on first start.

The UI is at `http://localhost:8080` and the API docs at
`http://localhost:8000/api/docs`. Uploads POST to `/api/projects/{project_id}/uploads`
and land as a queued ingestion run; the `GET` listing on the same path derives each
row's status from its latest run.

```powershell
docker compose -f deploy/docker-compose.yml down
```

stops the system; the named volumes survive it. After changing code, rebuild with:

```powershell
docker compose -f deploy/docker-compose.yml up -d --build
```

This recreates the affected services. The dependency layer is cached, so only the
project itself is reinstalled.

The system is machine-global: one running system at a time, owned by the checkout that
started it. Run `down` before starting it from another checkout or worktree, whose
bind-mounted configs would otherwise dangle.

A Vite dev server (`npm run dev` in `web/` with
`VITE_API_BASE_URL=http://localhost:8000/api`) still works against the compose API for
ad-hoc UI work, but it is not the runbook path.

Do not change `GARAGE_DEFAULT_SECRET_KEY` after first start: Garage binds its stored
layout to the secret it was created with, startup fails with a different one, and the
metadata volume must be wiped to recover.

RabbitMQ state lives on the named `rabbitmqdata` volume, so queues and vhosts survive a
`docker compose up -d --force-recreate rabbitmq`. This volume was introduced after the
broker had run without one: recreating the container discards that old anonymous volume
once, and the `rag_test` and `rag_e2e` vhosts are recreated by their suites' bootstraps.

## Test

Tests need the compose services up: the real Postgres for every suite (never SQLite),
plus RabbitMQ for the outbox/worker integration tests and Garage for the storage,
uploads, and ingestion suites (the upload and ingest paths read and write real bytes).
The `engine` fixture creates a disposable `rag_test` database, applies all migrations,
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