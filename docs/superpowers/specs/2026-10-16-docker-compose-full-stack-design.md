# Docker Compose full-stack runtime - Design

Date: 2026-10-16
Status: Design round complete (2026-10-16); implementation pending.
Source of truth: the README runbook as it stands and the S3 spec
(`2026-10-12-s3-upload-ingestion-design.md`). Where those disagree with this document on
runtime and packaging topics, this document wins; where it is silent, they govern.

## 1. Context

Today compose provides infra only (Postgres, RabbitMQ, Garage); the app tier runs natively on
the Windows host - uvicorn, a solo-pool Celery worker, the outbox dispatcher, and the Vite
dev server - with schema migrations as a manual README step (`alembic upgrade head` before
first boot). This round makes compose the whole system: `docker compose up -d` starts
everything, on Linux, with no manual steps; `docker compose down` stops it. The app tier
never runs natively again.

What deliberately does not change is the development loop. pytest drives the app
in-process against the compose infra exactly as today (its disposable `rag_test` database
and broker vhost); vitest is unaffected; and the Playwright journey keeps its isolated
fixture environment (`rag_e2e` database and vhost, uvicorn on 8001, vite on 5173) - the same
isolation philosophy pytest already follows. Only the *system's runtime* moves into
containers.

Environment (verified 2026-10-16): Windows; Docker 29.6.2 + Compose v5.3.1; Python 3.14 venv
at `.venv`; Node 24.14.1.

## 2. Decisions (2026-10-16 design round)

1. **Compose is the only runtime; there are no profiles.** The app services join the default
   compose set, so plain `up -d` starts the whole system. A profile-based design (infra by
   default, `--profile app` opt-in) was considered and rejected in the design round: the
   native app-tier workflow is retired, so nothing needs an infra-only mode, and two modes is
   one more than the system needs. Consequences: the README's native-run sections are
   removed, and code changes are exercised in the running system via
   `docker compose up -d --build` (pytest stays the fast loop; sections 9 and 11).
2. **Everything the backend serves lives under `/api`.** `main.py` includes each router with
   `prefix="/api"`, moves health to `/api/health`, and registers the docs surfaces under
   `/api/docs`, `/api/redoc`, `/api/openapi.json`. Two reasons: the SPA and the API collide
   on `/projects` (page route vs resource path), so a root-level reverse proxy cannot
   distinguish browser navigation from API calls; and an explicit prefix makes the boundary
   between pages and API legible in every URL. nginx passes `/api/...` through unchanged -
   no rewriting, because the backend genuinely serves these paths. All API-path references
   in tests and e2e update mechanically (section 5).
3. **One backend image, four services.** `backend/Dockerfile` builds a single image
   (`python:3.14-slim`, `pip install .`, non-root user); the compose services
   `one-off-initialization`, `api`, `worker`, and `dispatcher` share it through per-service
   `command:` overrides. No per-role images to keep in sync.
4. **The compose migration step is named `one-off-initialization`** (design-round naming
   decision): the name communicates the container's lifecycle role - it runs once per `up`,
   exits, and gates the app services - rather than one implementation detail, and leaves a
   natural home for future startup tasks. The script it runs stays `scripts/migrate.py`,
   which names what that script does (section 6).
5. **Migrations are a one-shot ordered step, never app-startup behavior.** Three app
   containers racing `alembic upgrade head` would have no cross-process coordination; a
   failed migration must halt startup loudly (nothing downstream starts) instead of
   crash-looping the fleet; and the step stays auditable. So `api`/`worker`/`dispatcher`
   declare `depends_on: one-off-initialization: {condition: service_completed_successfully}`.
   This is the compose incarnation of the standard production migration pattern
   (section 10).
6. **The web is nginx serving the built SPA plus a reverse proxy.** The browser loads the
   SPA from `http://localhost:8080` and every API call resolves to the same origin (the baked
   base URL is the relative `/api`), so the compose path never makes a cross-origin request:
   no CORS involvement, and no hostname baked into the bundle. nginx forwards `/api/...`
   to `api:8000` server-side. Port 8080 avoids privileged/conflicting port 80 on Windows
   hosts and leaves 5173 (the e2e fixture port) free to run concurrently with the system.
   nginx's `client_max_body_size` must cover `max_upload_mb` (25) - its 1 MB default would
   reject every real upload.
7. **Broker credentials stay `guest`, explicitly permitted off-loopback.** A mounted
   `deploy/rabbitmq.conf` sets `loopback_users.guest = false`, making guest auth from the
   compose network deterministic instead of dependent on image defaults. Dev-grade by
   design; `config.py` already refuses the development JWT and S3 secrets whenever
   `environment=production`, so production-grade broker auth is future work (section 10).
   The `CORSMiddleware` stays in the app for the other paths: the e2e setup (page on 5173,
   API on 8001) is still cross-origin and depends on it, and `test_cors.py` keeps guarding
   it. In the compose path it is simply never triggered.
8. **The web's default API base becomes the relative `/api`.** `VITE_API_BASE_URL ?? "/api"`.
   Verified against the installed RTK: `fetchBaseQuery` string-joins via `joinUrls`
   (`/api` + `/projects` -> `/api/projects`), and `fetch` resolves the relative URL against
   the page origin - so the app's natural mode is same-origin, exactly how the system is
   served. e2e overrides it with `http://localhost:8001/api`; the MSW handlers mirror the
   `/api` paths (they match full paths). No origin or port is baked into the bundle.
9. **Test isolation is preserved end to end.** pytest keeps `rag_test`; the Playwright
   journey keeps `rag_e2e` (own database, own broker vhost, own ports 8001/5173) because
   running it against the system's real database would mutate real data and make the suite
   non-repeatable - the same reason pytest never touches the dev database. Both suites share
   only the compose infra. Packaging correctness is proven separately by a compose smoke run
   (section 8), so e2e does not have to test the images.

## 3. Compose topology (`deploy/docker-compose.yml`)

| Service | Image / source | Command | Ports | Depends on |
|---|---|---|---|---|
| db | pgvector/pgvector:pg17 (unchanged) | - | 5432 | - |
| rabbitmq | rabbitmq:3.13-management, mounts `rabbitmq.conf` | - | 5672, 15672 | - |
| garage | dxflrs/garage:v2.3.0 (unchanged) | - | 3900, 3903 | - |
| one-off-initialization | backend image | `python scripts/migrate.py` | - | db healthy |
| api | backend image | `uvicorn app.main:app --host 0.0.0.0 --port 8000` | 8000 | db healthy; one-off-initialization completed |
| worker | backend image | `celery -A app.workers.celery_app worker -Q ingestion,embed` | - | db healthy; one-off-initialization completed; rabbitmq healthy |
| dispatcher | backend image | `python -m app.workers.dispatcher` | - | db healthy; one-off-initialization completed; rabbitmq healthy |
| web | web image (nginx) | - | 8080 | api healthy |

Startup chain: db healthy -> one-off-initialization applies migrations and exits 0 ->
api/worker/dispatcher start -> api passes its healthcheck -> web starts. The worker keeps
Celery's Linux default prefork pool - the Windows-only `--pool=solo` exists for native
Windows, and the worker's own startup handler already disposes its boot connection
before the pool forks (`app/workers/signals.py`: "safe under prefork, where children
re-connect through their own pool"), so the pool is designed for this.

App-tier environment (compose `environment:`), pointing at the in-network service names:

- `RAG_DATABASE_URL=postgresql+psycopg://rag:rag@db:5432/rag`
- `RAG_BROKER_URL=amqp://guest:guest@rabbitmq:5672//`
- `RAG_S3_ENDPOINT=http://garage:3900`

The one-off-initialization service needs only `RAG_DATABASE_URL`. Every other setting keeps
its `config.py` defaults (the Garage key, secret, region, and bucket already match the
compose service). Build contexts are `../backend` and `../web` relative to `deploy/`.

Healthchecks: the api container gets
`python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"`
(curl is absent from the slim image). worker and dispatcher deliberately get none: the
broker's connect-on-startup retry keeps them alive, and neither exposes a cheap probe
surface. Garage gets no boot-order dependency from the app tier - the storage client is
created lazily per process, so an upload immediately after `up` can race Garage's startup;
the failure is a user-visible error, not a crash, and the runbook's "wait for healthy"
covers it (section 11).

Volumes, the project name (`rag`), and the db/rabbitmq/garage definitions are unchanged;
rabbitmq additionally mounts `./rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf`.

## 4. Images

### 4.1 `backend/Dockerfile`

`FROM python:3.14-slim`; `WORKDIR /app`; copy `pyproject.toml`, `app/`, `alembic/`,
`alembic.ini`, `scripts/`; `RUN pip install --no-cache-dir .`; a dedicated non-root user;
`EXPOSE 8000`; default `CMD` the uvicorn command from section 3. `backend/.dockerignore`
keeps local state out of the image: `.venv`, `.env`, `__pycache__`, `.mypy_cache`,
`.pytest_cache`, `.ruff_cache`, `tests/`, logs. The `.env` exclusion matters twice over:
compose is the single config source for containers, and no local settings ride into images.

### 4.2 `web/Dockerfile` and `web/nginx.conf`

Two stages. Build: `FROM node:24-alpine` (matches the verified Node 24 toolchain),
`npm ci`, copy sources, `npm run build` with `VITE_API_BASE_URL=/api` supplied as a build
argument. Serve: `FROM nginx:1-alpine`, copy `dist/` into the nginx root plus the conf.
The build context cannot reach outside `web/`, which is why `nginx.conf` lives in `web/`
rather than `deploy/`.

The nginx conf invariants:

- `client_max_body_size 26m;` - covers `max_upload_mb` (25) with headroom.
- `location /api/` proxies to the api service with the request URI passed through
  unchanged (the backend serves the `/api` prefix itself), the standard forwarded headers
  (`Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`), and Docker's embedded DNS
  resolver (`resolver 127.0.0.11 valid=10s;` with the upstream name in a variable) so a
  recreated api container does not leave nginx pinned to a dead IP - with a static
  `proxy_pass http://api:8000`, nginx resolves once at config load and 502s after api is
  rebuilt via `up -d --build`.
- `location / { try_files $uri $uri/ /index.html; }` - SPA history-routing fallback.
- No CORS headers anywhere: the compose path is same-origin (decision 6).

`web/.dockerignore`: `node_modules`, `dist`, `test-results`, `e2e`, logs.

## 5. API surface change (`/api` prefix)

`app/main.py`:

```python
app = FastAPI(
    title="rag-mvp",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.include_router(identity_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(sources_router, prefix="/api")


@app.get("/api/health")
```

Affected call sites - mechanical path updates only, no assertion changes:

- Backend tests: `tests/identity/` (auth API, users/me, workspaces), `tests/projects/`,
  `tests/sources/test_uploads_api.py`, `tests/test_cors.py`, `tests/test_health.py`,
  `tests/test_smoke_e2e.py`.
- Web: `src/app/api.ts` default becomes `"/api"`; `src/test/handlers.ts` MSW paths gain the
  prefix (`*/auth/register` becomes `*/api/auth/register`, and so on - msw matches full
  paths).
- E2e: `playwright.config.ts` readiness URL becomes `http://localhost:8001/api/health` and
  its web entry sets `VITE_API_BASE_URL="http://localhost:8001/api"`;
  `e2e/journey.spec.ts`'s direct API call gains the prefix. The page-URL assertions on
  `http://localhost:5173/` are page routes, not API calls, and stay as they are.

## 6. The one-off-initialization service

`backend/scripts/migrate.py` mirrors the established pattern of `scripts/e2e_db.py`'s
bootstrap: build the alembic `Config` explicitly and call
`config.set_main_option("sqlalchemy.url", get_settings().database_url)` - the URL flows
from the app settings (compose's `RAG_DATABASE_URL`) through explicit code, so
`alembic/env.py` never reads the environment and the existing guard invariant - "a stray
`RAG_DATABASE_URL` cannot redirect a configured migration run" (`tests/test_alembic.py`) -
stays intact and green.

Compose properties: `restart: "no"`; depends on db healthy; the app services wait on
`service_completed_successfully`. Idempotent by construction - alembic at head is a no-op,
so every subsequent `up` re-runs the container cheaply and harmlessly. Failure is loud:
compose reports the exited-with-error container and starts nothing downstream.

New test: `backend/tests/test_migrate_script.py` - run the script's migration path against a
scratch database derived from the configured test URL (the `tests/test_alembic.py`
pattern) and assert the schema reaches head (the `alembic_version` table reports the head
revision).

## 7. Broker access from the compose network

`deploy/rabbitmq.conf`:

```ini
# The app services connect as guest from other containers; the broker's default
# loopback restriction refuses that, so guest is explicitly allowed off-loopback.
loopback_users.guest = false
```

Mounted at `/etc/rabbitmq/rabbitmq.conf`, which the official image reads by default. This
is a dev-stack credential posture, accepted deliberately (decision 7): one credential set
serves the host suites and the containers alike, there is no user-provisioning step, and
the production-secret discipline already lives in `config.py`'s validators.

## 8. Testing strategy

- **Backend**: all gates per AGENTS.md - `ruff check .`, `ruff format --check .`,
  `mypy app tests`, `pytest` - plus the new migrate-script test. The API-path updates are
  the only changes to existing tests.
- **Web**: `npm run test` (vitest; the handlers carry the new paths), `npm run lint`,
  `npm run format:check` (prettier pins LF through `.gitattributes`).
- **E2e**: `npm run e2e`, unchanged in mechanism - it starts its own fixtures. It may now
  run while the compose system is up, because its ports (8001, 5173) no longer collide
  with anything the system uses (8000, 8080).
- **Packaging smoke** (manual, scripted in the implementation plan): `docker compose up -d
  --build`; `GET http://localhost:8080/api/health` through nginx and
  `http://localhost:8000/api/docs` directly; register and log in through the UI at
  `http://localhost:8080`; upload a real file and watch the run reach `ready` - exercising
  one-off-initialization, api, dispatcher, broker, worker, and Garage in one pass; then a
  fresh-volume variant under a scratch project name proving the system boots from nothing
  with zero manual steps; `docker compose down`.
- **Compose config sanity**: `docker compose -f deploy/docker-compose.yml config` parses
  and shows the expected service graph.

## 9. Runbook (README) changes

- New **"Run the whole system"** section: `docker compose -f deploy/docker-compose.yml
  up -d` starts everything; the UI is at `http://localhost:8080`, the API docs at
  `http://localhost:8000/api/docs`; `docker compose -f deploy/docker-compose.yml down`
  stops it. After changing code, `up -d --build` recreates the affected services (layer
  caching keeps rebuilds to seconds).
- Removed: "Migrate the development database" (the one-off-initialization service owns
  schema setup), "Run the API", and "Run the ingestion workers" - the app tier never runs
  natively.
- "Setup" is reworded: the venv now serves the test suites and migrations authoring, not
  the running system; `npm install` similarly serves the web toolchain and e2e.
- "Test" is unchanged.
- One-line note: a Vite dev server (`npm run dev` with
  `VITE_API_BASE_URL=http://localhost:8000/api`) still works against the compose API for
  ad-hoc UI work - its ports do not collide with the system's - but it is not the runbook
  path.

## 10. Path to production

The one-off initialization step is the compose incarnation of the standard production
migration pattern, so a later deployment translates rather than redesigns:

| Deployment style | The same step becomes |
|---|---|
| docker compose on a server | the `one-off-initialization` service, unchanged |
| Kubernetes | an init container, or a pre-deploy Job / Helm pre-upgrade hook / Argo pre-sync hook |
| CI/CD pipeline | an explicit migration stage that must pass before new app versions roll out |
| Single-container PaaS | a release-phase command or entrypoint (safe only because there is exactly one container) |

The invariant carried into all of them: **application containers never migrate the schema
themselves** - replicas would race, a failed migration must halt the rollout loudly, and
migrations stay an auditable deployment action. Production disciplines deliberately left
for that later round: expand-contract migrations for zero-downtime rollouts, advisory locks
against concurrent migrators, real secret management, and broker credentials beyond guest.
The compose file built here doubles as the deployment blueprint.

## 11. Risks and accepted costs

- **Seeing a backend change in the running system requires an image rebuild**
  (`up -d --build`, seconds with layer caching). Accepted by the compose-only decision;
  pytest remains the fast feedback loop, and the system run is for whole-system behavior.
- **Dev-mode containers (bind mounts, polling hot-reload) are deliberately absent.** They
  exist in the industry but cost complexity, and file watching does not propagate across
  Windows bind mounts anyway; the design round chose tests plus rebuild instead.
- **guest-off-loopback is a dev posture.** Accepted for the local stack; production broker
  auth is future work (section 10).
- **No Garage boot ordering.** The first upload right after `up` can race Garage's startup;
  the lazy storage client turns it into a user-visible error, not a crash. Covered by
  "wait for containers to be healthy" in the runbook.
- **Hub-pinned base images** (`python:3.14-slim`, `node:24-alpine`, `nginx:1-alpine`) mean
  image builds depend on Docker Hub availability. Accepted for a local stack.
- **The e2e fixtures still run the app tier natively** (uvicorn, a solo-pool worker, the
  dispatcher as Playwright `webServer`s). That is test tooling, not the system; moving it
  into containers is the CI-idea below.

## 12. Out of scope

- Production deployment (TLS, domains, secrets management, CI/CD).
- Containerized e2e as a CI packaging test - running the existing journey against a
  composed stack in CI, where databases are disposable. To be recorded in the backlog at
  task completion; the compose smoke run covers the packaging gap meanwhile.
- Kubernetes manifests or Helm charts.
- Dev-mode containers with bind mounts and polling.

## 13. Done when

- On a fresh volume set, `docker compose -f deploy/docker-compose.yml up -d --build`
  produces a working system with zero manual steps: the UI at `http://localhost:8080`, the
  API docs at `http://localhost:8000/api/docs`, and an upload from the browser reaches
  `ready` through the real dispatcher, broker, worker, and Garage.
- `docker compose down` stops everything; the named volumes survive it.
- All gates pass after the path updates: `ruff check .`, `ruff format --check .`,
  `mypy app tests`, `pytest` (including the new migrate-script test), `npm run test`,
  `npm run lint`, `npm run format:check`, `npm run e2e`.
- The README describes the single-command runbook with no native app-tier instructions.
