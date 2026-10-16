# Docker Compose full-stack runtime - Design

Date: 2026-10-16
Status: Design round complete (2026-10-16); review round fixes folded in (2026-10-16);
implementation pending.
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
and broker vhost); vitest is unaffected except for one pinned env value in
`vite.config.ts` (decision 8); and the Playwright journey keeps its isolated
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
   (`python:3.14-slim`, pip install in two layers - section 4.1 - non-root user); the
   compose services
   `one-off-initialization`, `api`, `worker`, and `dispatcher` share it through per-service
   `command:` overrides. No per-role images to keep in sync. The compose file defines the
   image exactly once - an `x-backend` anchor carries the `build`/`image` mapping and each
   service merges it (section 3) - so `up --build` cannot produce four divergent builds.
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
   to `api:8000` server-side (the api runs uvicorn with `--forwarded-allow-ips=*` so the
   forwarded headers are honored - by default uvicorn trusts `X-Forwarded-*` from
   loopback clients only). Port 8080 avoids privileged/conflicting port 80 on Windows
   hosts and leaves 5173 (the e2e fixture port) free to run concurrently with the system.
   nginx's `client_max_body_size` must cover `max_upload_mb` (25) - its 1 MB default would
   reject every real upload.
7. **Broker credentials stay `guest`, with the off-loopback posture pinned explicitly.**
   The official image already disables the guest loopback restriction itself - its
   bundled `/etc/rabbitmq/conf.d/10-defaults.conf` sets `loopback_users.guest = false`
   (verified in the running container) - so guest auth from the compose network works
   without our config. The mounted `deploy/rabbitmq.conf` sets the same value so the
   posture is an explicit property of this stack's tree rather than an inherited image
   default that an image update could change. Dev-grade by design; `config.py` already
   refuses the development JWT and S3 secrets whenever `environment=production`, so
   production-grade broker auth is future work (section 10).
   The `CORSMiddleware` stays in the app for the other paths: the e2e setup (page on 5173,
   API on 8001) is still cross-origin and depends on it, and `test_cors.py` keeps guarding
   it. In the compose path it is simply never triggered.
8. **The web's default API base becomes the relative `/api`.** `VITE_API_BASE_URL ?? "/api"`.
   Verified against the installed RTK: `fetchBaseQuery` string-joins via `joinUrls`
   (`/api` + `/projects` -> `/api/projects`), and `fetch` resolves the relative URL against
   the page origin - so the app's natural mode is same-origin, exactly how the system is
   served. e2e overrides it with `http://localhost:8001/api`; the MSW handlers carry the
   `/api` paths too, keeping the fixtures in step with the real surface (`*/auth/register`
   would still match an `/api/auth/register` request, because `*` matches any prefix -
   mirroring the real paths is fixture honesty, not a matching requirement). No origin or
   port is baked into the bundle.

   The relative default cannot serve the vitest environment: RTK Query builds a `Request`
   before `fetch` runs, and Node's `Request` rejects relative URLs (`Failed to parse URL
   from /api/projects`, verified under the project's vitest). `vite.config.ts` therefore
   pins `VITE_API_BASE_URL` for tests through `test.env` - `http://localhost:3000/api`,
   the jsdom page origin with the same prefix - so the suite keeps working against an
   absolute URL there. Verified: `test.env` values reach `import.meta.env`, and the
   resulting `Request` parses.
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
| api | backend image | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --forwarded-allow-ips=*` | 8000 | db healthy; one-off-initialization completed |
| worker | backend image | `celery -A app.workers.celery_app worker -Q ingestion,embed --concurrency 2` | - | db healthy; one-off-initialization completed; rabbitmq healthy |
| dispatcher | backend image | `python -m app.workers.dispatcher` | - | db healthy; one-off-initialization completed; rabbitmq healthy |
| web | web image (nginx) | - | 8080 | api healthy |

Startup chain: db healthy -> one-off-initialization applies migrations and exits 0 ->
api/worker/dispatcher start -> api passes its healthcheck -> web starts. The worker keeps
Celery's Linux default prefork pool - the Windows-only `--pool=solo` exists for native
Windows, and the worker's own startup handler already disposes its boot connection
before the pool forks (`app/workers/signals.py`: "safe under prefork, where children
re-connect through their own pool"), so the pool is designed for this.

The worker pins `--concurrency 2`: Celery's default is one child per CPU in the Docker
VM, and each child holds its own SQLAlchemy pool, so the default could crowd the
100-connection Postgres maximum this stack shares with the test suites. Two children keep
dev-grade parallelism with a bounded connection count.

The long-running app services (`api`, `worker`, `dispatcher`) run with `init: true`.
Otherwise the dispatcher is PID 1 with no SIGTERM handler, and PID 1 ignores unhandled
signals - every `down` would wait out Docker's stop timeout and SIGKILL it. uvicorn and
celery handle SIGTERM themselves; the init process is harmless for them and reaps
zombies besides.

The image behind the four backend services is defined exactly once: an `x-backend`
anchor carries `build: {context: ../backend}` and `image: rag-backend`, and each service
merges the anchor with its own `command:` (decision 3), so one build serves all four.

App-tier environment (compose `environment:`), pointing at the in-network service names:

- `RAG_DATABASE_URL=postgresql+psycopg://rag:rag@db:5432/rag`
- `RAG_BROKER_URL=amqp://guest:guest@rabbitmq:5672//`
- `RAG_S3_ENDPOINT=http://garage:3900`

The one-off-initialization service needs only `RAG_DATABASE_URL`. Every other setting keeps
its `config.py` defaults (the Garage key, secret, region, and bucket already match the
compose service). Build contexts are `../backend` and `../web` relative to `deploy/`.

Healthchecks: the api container gets
`python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"`
(curl is absent from the slim image), with `interval: 5s`, `timeout: 5s`, `retries: 10`,
`start_period: 10s`, `start_interval: 1s` - Docker's default 30-second interval would
otherwise hold `web` back for half a minute on every `up`. worker and dispatcher
deliberately get none: the broker's connect-on-startup retry keeps them alive, and
neither exposes a cheap probe surface. Garage gets a healthcheck of
`["CMD", "/garage", "status"]` - the CLI control command, which talks to the local node
over RPC and exits 0 only when the node answers (verified against the image: a scratch
container reports its node under "HEALTHY NODES") - so the runbook's "wait for healthy"
names something observable. The app tier still takes no boot-order dependency on Garage:
the storage client is created lazily per process, so an upload immediately after `up` can
race Garage's readiness; the failure is a user-visible error, not a crash (section 11).

Volumes, the project name (`rag`), and the db/rabbitmq/garage definitions are unchanged;
rabbitmq additionally mounts `./rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf`.

The project name and the published host ports are machine-global: exactly one system
runs at a time, owned by whichever checkout last ran `up -d` (its bind-mounted config
files serve that stack), and another checkout - or worktree - that wants the system must
`down` it first. The test suites are unaffected: they target the infra's host ports and
do not care which checkout started them. Observed in the wild: the running stack's
`garage.toml` mount points into a since-removed worktree, and `docker exec ... /garage
status` fails on the dangling mount while the server keeps serving from startup state.

## 4. Images

### 4.1 `backend/Dockerfile`

`FROM python:3.14-slim`; `WORKDIR /app`; a dedicated non-root user; `EXPOSE 8000`;
default `CMD` the uvicorn command from section 3. The install is split into two layers
so code-only rebuilds stay fast: first copy `pyproject.toml` alone and install the
dependency set it declares into a cached layer (the mechanism is the implementation's
choice - building the project from the manifest alone, or parsing the dependency list
out of it); then copy `app/`, `alembic/`, `alembic.ini`, `scripts/` and
`RUN pip install --no-deps --no-cache-dir .`. A single `pip install .` placed after the
full source copy would resolve and reinstall every dependency on every code change, and
the runbook's "rebuilds in seconds" claim depends on the split; the packaging smoke
verifies it (section 8). `backend/.dockerignore` keeps local state out of the image:
`.venv`, `.env`, `__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `tests/`,
logs. The `.env` exclusion matters twice over: compose is the single config source for
containers, and no local settings ride into images.

### 4.2 `web/Dockerfile` and `web/nginx.conf`

Two stages. Build: `FROM node:24-alpine` (matches the verified Node 24 toolchain),
`npm ci`, copy sources, `npm run build` - no build argument is supplied, because the
relative `/api` default already lives in `src/app/api.ts` and one source of truth beats
two. Serve: `FROM nginx:1-alpine`, copy `dist/` into the nginx root plus the conf.
The build context cannot reach outside `web/`, which is why `nginx.conf` lives in `web/`
rather than `deploy/`.

The nginx conf invariants:

- `client_max_body_size 26m;` - covers `max_upload_mb` (25) with headroom.
- `location /api/` proxies to the api service with the request URI passed through
  unchanged (the backend serves the `/api` prefix itself), the standard forwarded headers
  (`Host $http_host` - not `$host`, which drops the `:8080` port - plus `X-Real-IP`,
  `X-Forwarded-For`, `X-Forwarded-Proto`), and Docker's embedded DNS
  resolver (`resolver 127.0.0.11 valid=10s;` with the upstream name in a variable) so a
  recreated api container does not leave nginx pinned to a dead IP - with a static
  `proxy_pass http://api:8000`, nginx resolves once at config load and 502s after api is
  rebuilt via `up -d --build`.
- The forwarded headers are actually honored: the api command runs
  `--forwarded-allow-ips=*` (section 3) because uvicorn trusts `X-Forwarded-*` only from
  loopback clients by default. Trusting the compose network is the same dev posture as
  the guest broker credentials (decision 7), and it matters only the day the app reads
  scheme or client IP.
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
  `tests/test_smoke_e2e.py`, and `tests/helpers.py` (the shared register-and-team
  helper calls the API directly).
- New backend test `tests/test_api_prefix.py`: every route in `app.routes` must start with
  `/api`, so a future router included without the prefix fails the suite instead of
  hiding behind nginx.
- Web: `src/app/api.ts` default becomes `"/api"`, and its doc comment plus
  `src/env.d.ts` are reworded to describe the relative default (both currently document
  `http://localhost:8000`); `vite.config.ts` gains the pinned vitest env (decision 8);
  `src/test/handlers.ts` MSW paths gain the prefix (`*/auth/register` becomes
  `*/api/auth/register`, and so on - fixture honesty, not a matching requirement, since
  `*` matches any prefix).
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

Like `scripts/e2e_db.py`, the script resolves `alembic.ini` and the `alembic/` directory
relative to its own file rather than the working directory, so it runs from anywhere; in
the container that is `/app` (the image `WORKDIR`), and the compose `command:` needs no
`working_dir:` override. The script's exit status is what compose gates the app services
on, so the failure path - a failing migration exits non-zero - is part of the contract.

Compose properties: `restart: "no"`; depends on db healthy; the app services wait on
`service_completed_successfully`. Idempotent by construction - alembic at head is a no-op,
so every subsequent `up` re-runs the container cheaply and harmlessly. Failure is loud:
compose reports the exited-with-error container and starts nothing downstream.

New test: `backend/tests/test_migrate_script.py` - create a scratch database from the
configured test URL (the `tests/test_alembic.py` pattern), run the script as a real
subprocess (`python scripts/migrate.py`) with `RAG_DATABASE_URL` pointed at it, from a
working directory outside `backend/`, and assert the schema reaches head (the
`alembic_version` table reports the head revision). The subprocess covers the actual
entry path - settings lookup, `alembic.ini` resolution, exit status - where an in-process
call would test a function the container never runs.

## 7. Broker access from the compose network

`deploy/rabbitmq.conf`:

```ini
# The app services connect as guest from other containers. The image's bundled
# 10-defaults.conf already allows guest off-loopback; this file pins that posture in
# our tree so an image update cannot silently withdraw it.
loopback_users.guest = false
```

Mounted at `/etc/rabbitmq/rabbitmq.conf`, which the official image reads by default
(merged with its bundled `/etc/rabbitmq/conf.d/`). The mount is not what unlocks
container-to-broker guest auth - the image's own `10-defaults.conf` already sets
`loopback_users.guest = false`, verified in the running container - it makes the posture
an explicit property of this stack's tree instead of an inherited default (decision 7).
This is a dev-stack credential posture, accepted deliberately: one credential set serves
the host suites and the containers alike, there is no user-provisioning step, and the
production-secret discipline already lives in `config.py`'s validators.

## 8. Testing strategy

- **Backend**: all gates per AGENTS.md - `ruff check .`, `ruff format --check .`,
  `mypy app tests`, `pytest` - plus the new migrate-script test. The API-path updates are
  the only changes to existing tests.
- **Web**: `npm run test` (vitest; the handlers carry the new paths, and `vite.config.ts`
  pins `VITE_API_BASE_URL` because Node's `Request` rejects the relative default -
  decision 8), `npm run lint`, `npm run format:check` (prettier pins LF through
  `.gitattributes`).
- **E2e**: `npm run e2e`, unchanged in mechanism - it starts its own fixtures. It may now
  run while the compose system is up, because its ports (8001, 5173) no longer collide
  with anything the system uses (8000, 8080).
- **Packaging smoke** (manual, scripted in the implementation plan): `docker compose up -d
  --build`; `GET http://localhost:8080/api/health` through nginx and
  `http://localhost:8000/api/docs` directly; register and log in through the UI at
  `http://localhost:8080`; upload a real file and watch the run reach `ready` - exercising
  one-off-initialization, api, dispatcher, broker, worker, and Garage in one pass; then a
  second `up -d --build` after a one-line source change, which must skip the dependency
  layer (section 4.1); then a fresh-volume variant under a scratch project name
  (`docker compose -p rag-smoke up -d --build`), run with the main project `down`ed
  because both publish the same host ports, proving the system boots from nothing with
  zero manual steps; `docker compose down` of whichever stack is up at the end.
- **Compose config sanity**: `docker compose -f deploy/docker-compose.yml config` parses
  and shows the expected service graph.

## 9. Runbook (README) changes

- New **"Run the whole system"** section: `docker compose -f deploy/docker-compose.yml
  up -d` starts everything; the UI is at `http://localhost:8080`, the API docs at
  `http://localhost:8000/api/docs`; `docker compose -f deploy/docker-compose.yml down`
  stops it. After changing code, `up -d --build` recreates the affected services (the
  dependency layer is cached; the rebuild reinstalls only the project itself - section
  4.1). The section also notes that the system is machine-global: one running system at
  a time, owned by the checkout that started it - `down` before starting it from another
  checkout or worktree, whose bind-mounted configs would otherwise dangle.
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
  (`up -d --build`, seconds: the dependency layer is cached and only the project
  reinstall reruns - section 4.1). Accepted by the compose-only decision; pytest remains
  the fast feedback loop, and the system run is for whole-system behavior.
- **Dev-mode containers (bind mounts, polling hot-reload) are deliberately absent.** They
  exist in the industry but cost complexity, and file watching does not propagate across
  Windows bind mounts anyway; the design round chose tests plus rebuild instead.
- **guest-off-loopback is a dev posture.** Accepted for the local stack; production broker
  auth is future work (section 10).
- **No Garage boot ordering.** The first upload right after `up` can race Garage's
  readiness; the lazy storage client turns it into a user-visible error, not a crash.
  The `/garage status` healthcheck (section 3) makes the runbook's "wait for healthy"
  an observable wait, but the race itself stays accepted.
- **Hub-pinned base images** (`python:3.14-slim`, `node:24-alpine`, `nginx:1-alpine`) mean
  image builds depend on Docker Hub availability. Accepted for a local stack.
- **Image dependencies are resolved at build time, not locked.** There is no pip lock
  file, so `pip install` in the image resolves the freshest versions within
  `pyproject.toml`'s floors and can drift from the venv the suites run on. Accepted for a
  local stack; both environments sit behind the same floors.
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
