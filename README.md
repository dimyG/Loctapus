# RAG MVP

RAG MVP is a self-hosted "chat with your documents" system. Teams upload PDF and
DOCX files into shared projects, where they are parsed and indexed automatically;
users then ask questions in a per-project chat and get answers grounded in - and
citing - the uploaded documents. Everything runs on one machine (or a single
server) via Docker Compose, with no external service required beyond an optional
LLM provider key.

FastAPI + SQLAlchemy 2.0 + pgvector backend for a RAG MVP, sliced into incremental
deliverables. Identity (users, workspaces, teams), projects, the upload+ingestion
pipeline (upload -> parse -> chunk -> embed), retrieval (vector + full-text search
fused with RRF), and grounded question answering (the chat UI) are done.

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
`backend/app/core/config.py`), with a `.env` file supported in `backend/`
(`backend/.env.example` lists the commonly set ones; the copy is gitignored).
The defaults target the compose services below, as seen from the host (the test
suites); the containers get their own addresses from the compose file. The
stack credentials (Postgres, RabbitMQ, Garage) interpolate into the compose file
from `deploy/.env` (`deploy/.env.example` is the template; the copy is
gitignored).

## Run the whole system

Two gitignored copies seed the stack, and both abort `up` when missing:

```powershell
copy deploy\.env.example deploy\.env
copy backend\.env.example backend\.env
docker compose -f deploy/docker-compose.yml up -d
```

`deploy/.env` carries every stack credential (Postgres, RabbitMQ, Garage);
`docker-compose.yml` interpolates each one as `${VAR:?...}`, so a missing file
or value stops `up` with an error naming the variable before any container
starts - no deployment can silently boot with the development credentials that
are public in this repository. `backend/.env` carries the app settings:
`RAG_JWT_SECRET` (token signing) and the Groq opt-in below; the api service
loads it as a required env file (the long `env_file` syntax needs Docker
Compose 2.24+), though only its existence is enforced: a `backend/.env` from
before this branch (or any copy missing `RAG_JWT_SECRET`) silently signs
tokens with the public development secret, so add the line from the template.
Both templates' values reproduce the historical development credentials, so
existing named volumes keep working unchanged; a public deployment must
generate fresh values instead (`openssl rand -hex 32`).

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
row's status from its latest run, and `DELETE` on
`/api/projects/{project_id}/uploads/{upload_id}` removes an upload with its indexed
content and stored bytes. Retrieval POSTs to
`/api/projects/{project_id}/retrieve` with `{"query": "...", "top_k": 10}` and answers
with fused, diversity-selected chunks from the project's indexed documents. The chat
(Ask tab on a project page) POSTs to `/api/projects/{project_id}/answer` with
`{"query": "..."}` and returns the grounded answer plus its cited chunks - the
question -> answer path runs fully from the browser.

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

Do not change `GARAGE_DEFAULT_SECRET_KEY` (in `deploy/.env`) after first start: Garage binds
its stored layout to the secret it was created with, startup fails with a different one,
and the metadata volume must be wiped to recover.

RabbitMQ state lives on the named `rabbitmqdata` volume, so queues and vhosts survive a
`docker compose up -d --force-recreate rabbitmq`. This volume was introduced after the
broker had run without one: recreating the container discards that old anonymous volume
once, and the `rag_test` and `rag_e2e` vhosts are recreated by their suites' bootstraps.

### Opting in to Groq

The default stack stays offline: `llm_provider` defaults to `stub`, so `/answer` returns
a fixed stub sentence grounded in the retrieved chunks. Copy `backend/.env.example` to
`backend/.env`, uncomment `RAG_LLM_PROVIDER=groq`, and paste your key into
`RAG_GROQ_API_KEY`. The compose `api` service reads that file when it starts (recreate
it with `docker compose up -d` to pick up changes; the long env-file syntax needs
Docker Compose 2.24+), as do local runs started from `backend/`; the compose-fixed
service addresses are unaffected. Answers then route through `openai/gpt-oss-20b` on
Groq; a provider failure answers 502. The pytest and e2e suites pin the stub provider,
so this file never makes them call Groq.

## Test

Tests need the compose services up: the real Postgres for every suite (never SQLite),
plus RabbitMQ for the outbox/worker integration tests and Garage for the storage,
uploads, and ingestion suites (the upload and ingest paths read and write real bytes).
The suites target the template's development credentials - pytest's defaults, the
Playwright config, and `backend/scripts/e2e_db.py` all pin `rag:rag` Postgres and
`guest:guest` RabbitMQ on localhost - so on a checkout that generated fresh
credentials (a public demo) run them with the documented overrides
(`RAG_TEST_DATABASE_URL`, the Playwright env) or from a dev machine instead.
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

## Hetzner deployment

Every push to `master` auto-deploys the demo server via GitHub Actions. Bootstrap,
secrets, rotation, and teardown live in the runbook: `deploy/hetzner/README.md`.

## Further reading

- Slice design: `docs/superpowers/specs/2026-10-06-roadmap.md`
- Follow-ups and deferred findings: `docs/backlog.md`