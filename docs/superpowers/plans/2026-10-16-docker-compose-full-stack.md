# Docker Compose full-stack runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `docker compose -f deploy/docker-compose.yml up -d` start the whole system (api, worker, dispatcher, web, migrations) with zero manual steps, and retire the native app-tier runbook.

**Architecture:** One backend image serves four compose services through `command:` overrides; a `one-off-initialization` container applies migrations and gates the app services via `service_completed_successfully`. The whole API moves under `/api` so nginx can split SPA routes from API calls without rewriting; nginx serves the built SPA and proxies `/api/` to the api service, re-resolving its address per request. Test isolation is untouched: pytest keeps `rag_test`, Playwright keeps its native fixtures on 8001/5173, and packaging is proven by a manual compose smoke run.

**Tech Stack:** Docker Compose (v5.3.1), Dockerfile (python:3.14-slim, node:24-alpine, nginx:1-alpine), FastAPI, Celery, nginx, Playwright, vitest/MSW.

**Spec:** `docs/superpowers/specs/2026-10-16-docker-compose-full-stack-design.md` (amended by the review round, commit `ef8e756`). The spec travels with this plan; executors read both.

## Global Constraints

- Ports: web `8080:80`, api `8000:8000` (published); one-off-initialization/worker/dispatcher publish none. E2e fixtures keep 8001 (api) and 5173 (vite); pytest keeps `rag_test`, e2e keeps `rag_e2e`, the system uses `rag` - all on the compose db.
- Compose app-tier env (exact): `RAG_DATABASE_URL=postgresql+psycopg://rag:rag@db:5432/rag`, `RAG_BROKER_URL=amqp://guest:guest@rabbitmq:5672//`, `RAG_S3_ENDPOINT=http://garage:3900`. one-off-initialization gets only `RAG_DATABASE_URL`. Every other setting keeps its `config.py` default.
- Base images: `python:3.14-slim`, `node:24-alpine`, `nginx:1-alpine`; db `pgvector/pgvector:pg17`, rabbitmq `rabbitmq:3.13-management`, garage `dxflrs/garage:v2.3.0` stay unchanged.
- nginx invariants: `client_max_body_size 26m;`, `location /api/` with the upstream name in a variable plus `resolver 127.0.0.11 valid=10s;`, request URI passed unchanged, `Host $http_host`, no CORS headers anywhere, `try_files $uri $uri/ /index.html;` for the SPA.
- Worker: default prefork pool, `--concurrency 2`, `-Q ingestion,embed`. api/worker/dispatcher run `init: true`; one-off-initialization runs `restart: "no"`. api command carries `--forwarded-allow-ips=*`.
- `CORSMiddleware` stays in the app untouched (e2e is still cross-origin); nginx adds no CORS headers.
- Python style (AGENTS.md): line length 110, keyword-only parameters, docstrings on every definition (private included) with a blank line after, comments start with a capital and end with a dot, no em dash, no `# type: ignore` unless necessary.
- Every text file is LF (`.gitattributes` pins it; new Dockerfiles, confs, and YAML included).
- Gates before any commit: `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest` (backend); `npm run test`, `npm run lint`, `npm run format:check` (web); `npm run e2e` where this plan says so.
- The compose project name `rag` and its host ports are machine-global: exactly one system runs at a time. The smoke task (7) needs the machine exclusively; all other tasks are plain file edits plus suites.
- Execution happens in a worktree (superpowers:using-git-worktrees); the worktree's compose stack owns the machine during Task 7.

## Review Focus

The five input classes or failure modes the spec implies but no task's tests exercise, most likely first:

1. **A future router included without the `/api` prefix** - nginx would hide it behind a 404. Test: `backend/tests/test_api_prefix.py` asserts every route on the assembled app starts with `/api` (Task 1, steps 1-4).
2. **The relative `/api` default under Node/vitest** - RTK Query builds a `Request` before `fetch`, and Node's `Request` rejects relative URLs, so every RTK test would fail as FETCH_ERROR. Test: the vitest suite itself, demonstrated red before the `test.env` pin and green after (Task 1, steps 6-7).
3. **A failed migration must stop the fleet loudly** - compose gates the app services on the script's exit status, so a failure must exit non-zero, not hang or exit 0. Test: `backend/tests/test_migrate_script.py` runs the script as a subprocess against an unreachable database and asserts a non-zero exit (Task 2).
4. **api recreated while web keeps running** - a static `proxy_pass` would leave nginx pinned to the api's dead IP, 502ing after `up -d --build`. Test: the smoke's rebuild step re-checks `GET http://localhost:8080/api/health` after recreating api (Task 7).
5. **An upload over the limit through the proxy** - nginx's 1 MB default would 413 every upload, and the backend's own 25 MB check must be the one users see. Test: the smoke uploads 25.5 MB (expects the backend's 422 copy) and 27 MB (expects nginx's 413) through port 8080 (Task 7).

---

### Task 1: The API surface moves under `/api`

One atomic concern: backend paths, backend test paths, web default, vitest pin, MSW paths, and the e2e config all change meaning together; any split leaves a red gate in between.

**Files:**
- Modify: `backend/app/main.py`
- Test (new): `backend/tests/test_api_prefix.py`
- Modify (path literals only): `backend/tests/helpers.py`, `backend/tests/identity/test_auth_api.py`, `backend/tests/identity/test_users_me.py`, `backend/tests/identity/test_workspaces_api.py`, `backend/tests/projects/test_projects_api.py`, `backend/tests/sources/test_uploads_api.py`, `backend/tests/test_cors.py`, `backend/tests/test_health.py`, `backend/tests/test_smoke_e2e.py`
- Modify: `web/src/app/api.ts`, `web/src/env.d.ts`, `web/vite.config.ts`, `web/src/test/handlers.ts`, `web/src/app/api.test.ts`
- Modify: `web/playwright.config.ts`, `web/e2e/journey.spec.ts`

**Interfaces:**
- Consumes: nothing new (the current unprefixed app).
- Produces: the `/api`-prefixed surface - `/api/auth/register`, `/api/auth/login`, `/api/auth/logout`, `/api/users/me`, `/api/workspaces`, `/api/workspaces/{workspace_id}/teams`, `/api/projects`, `/api/projects/public`, `/api/projects/{project_id}`, `/api/projects/{project_id}/uploads`, `/api/health`, `/api/docs`, `/api/redoc`, `/api/openapi.json`. Produces `API_BASE_URL = VITE_API_BASE_URL ?? "/api"` in `web/src/app/api.ts` (Tasks 4 and 5's nginx `location /api/` matches this surface).

- [ ] **Step 1: Write the failing route-prefix test**

`backend/tests/test_api_prefix.py`:

```python
"""The API surface lives entirely under the /api prefix."""

from starlette.routing import Route

from app.main import app


def test_every_route_is_under_api() -> None:
    """Check that no route (docs surfaces included) escapes the /api prefix nginx forwards."""

    paths = [route.path for route in app.routes if isinstance(route, Route)]
    assert paths, "no routes found on the assembled app"
    assert all(path.startswith("/api/") for path in paths), sorted(paths)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend; ..\.venv\Scripts\python -m pytest tests/test_api_prefix.py -v`
Expected: FAIL - the bare paths (`/auth/register`, `/health`, ...) do not start with `/api`.

- [ ] **Step 3: Move `app/main.py` under the prefix**

Apply the spec's section 5 exactly: `FastAPI(title="rag-mvp", docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json")`, `app.include_router(..., prefix="/api")` for identity/projects/sources, and the health decorator becomes `@app.get("/api/health")`. Nothing else in the file changes (CORS middleware included).

- [ ] **Step 4: Run the prefix test to verify it passes**

Run: `cd backend; ..\.venv\Scripts\python -m pytest tests/test_api_prefix.py -v`
Expected: PASS.

- [ ] **Step 5: Prefix the backend test paths and run the suite**

In the nine test files listed above, prepend `/api` to every `client.<verb>("/auth/...", "/users/me", "/workspaces...", "/projects...", "/health")` path literal (including `tests/helpers.py`'s register/team helper and `test_cors.py`'s three `/health` uses). Assertion values do not change. Run: `cd backend; ..\.venv\Scripts\python -m pytest`.
Expected: PASS (all suites).

- [ ] **Step 6: Change the web default and watch vitest fail**

In `web/src/app/api.ts`, change the default to `"/api"` and reword the export's comment (it currently documents `http://localhost:8000`; describe the relative same-origin default and the e2e/vitest overrides). Run: `cd web; npm run test`.
Expected: FAIL - RTK tests fail as FETCH_ERROR because Node's `Request` rejects the relative URL (`Failed to parse URL from /api/...`). This red run is the evidence for the pin in step 7.

- [ ] **Step 7: Pin the vitest env and finish the web edits**

In `web/vite.config.ts`, add to the `test` block:

```ts
    env: { VITE_API_BASE_URL: "http://localhost:3000/api" },
```

In `web/src/env.d.ts`, reword the comment to describe the relative default. In `web/src/test/handlers.ts` and the `server.use` override in `web/src/app/api.test.ts`, prefix every handler path (`*/auth/register` becomes `*/api/auth/register`, and so on; `*` would still match, this is fixture honesty). Run: `cd web; npm run test`.
Expected: PASS.

- [ ] **Step 8: Update the e2e config and run the journey**

In `web/playwright.config.ts`: the uvicorn webServer's `url` becomes `http://localhost:8001/api/health`, and the vite webServer's env becomes `VITE_API_BASE_URL: "http://localhost:8001/api"` (the worker/dispatcher envs stay). In `web/e2e/journey.spec.ts`: the direct `request.get("http://localhost:8001/projects", ...)` gains the prefix; the `waitForResponse` substring `"/auth/logout"` still matches `/api/auth/logout` and stays; page-URL assertions stay. `enforcement.spec.ts` and `ProjectPage.test.tsx` need no change (page routes and a hardcoded absolute probe URL). Run: `cd web; npm run e2e`.
Expected: PASS (both spec files).

- [ ] **Step 9: Full gates and commit**

Run: `cd backend; ..\.venv\Scripts\ruff check .; ..\.venv\Scripts\ruff format --check .; ..\.venv\Scripts\mypy app tests; ..\.venv\Scripts\python -m pytest` and `cd web; npm run test; npm run lint; npm run format:check`.
Expected: all green.

```bash
git add backend/app/main.py backend/tests web/src web/vite.config.ts web/playwright.config.ts web/e2e
git commit -m "feat: move the API surface under the /api prefix"
```

### Task 2: The one-off migration script

**Files:**
- Create: `backend/scripts/migrate.py`
- Test (new): `backend/tests/test_migrate_script.py`

**Interfaces:**
- Consumes: `get_settings().database_url` (`app.core.config`), the alembic `Config`/`command` pattern from `scripts/e2e_db.py`, and `_terminate_and_drop` from `tests/test_alembic.py`.
- Produces: `python scripts/migrate.py` with `RAG_DATABASE_URL` selecting the target database; exit 0 at head, non-zero on failure. Task 5's `one-off-initialization` runs exactly this command.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_migrate_script.py`:

```python
"""Tests for the compose one-off-initialization script."""

import os
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.db import make_engine
from tests.test_alembic import _terminate_and_drop

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEST_URL = "postgresql+psycopg://rag:rag@localhost:5432/rag_test"


def _head_revision() -> str:
    """Return the migration graph's single head revision."""

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return str(ScriptDirectory.from_config(config).get_current_head())


def _run_migrate(*, database_url: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the script as a real subprocess against ``database_url`` from ``cwd``."""

    env = {**os.environ, "RAG_DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, str(BACKEND_DIR / "scripts" / "migrate.py")],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_migrate_applies_head_from_any_cwd(*, tmp_path: Path) -> None:
    """Check that the script migrates a scratch database to head from outside backend/."""

    url = os.environ.get("RAG_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    db_name = f"{url.rsplit('/', 1)[1]}_migrate"
    scratch_url = f"{url.rsplit('/', 1)[0]}/{db_name}"

    admin = make_engine(database_url=admin_url).execution_options(isolation_level="AUTOCOMMIT")
    try:
        # Drop a leftover first so reruns after a failed run stay self-healing.
        _terminate_and_drop(admin=admin, db_name=db_name)
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))

        result = _run_migrate(database_url=scratch_url, cwd=tmp_path)
        assert result.returncode == 0, result.stderr

        scratch = make_engine(database_url=scratch_url)
        try:
            with scratch.connect() as conn:
                version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        finally:
            scratch.dispose()
        assert version == _head_revision()
    finally:
        _terminate_and_drop(admin=admin, db_name=db_name)
        admin.dispose()


def test_migrate_exits_nonzero_on_unreachable_database(*, tmp_path: Path) -> None:
    """Check that a failed migration exits non-zero - the status compose gates on."""

    result = _run_migrate(
        database_url="postgresql+psycopg://rag:rag@localhost:5433/rag_unreachable",
        cwd=tmp_path,
    )
    assert result.returncode != 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend; ..\.venv\Scripts\python -m pytest tests/test_migrate_script.py -v`
Expected: FAIL - `scripts/migrate.py` does not exist.

- [ ] **Step 3: Implement `backend/scripts/migrate.py`**

```python
"""Apply alembic migrations to the settings-selected database.

Run as ``python scripts/migrate.py`` (the compose ``one-off-initialization``
service): the URL flows from ``RAG_DATABASE_URL`` through the app settings into
alembic's config explicitly, so ``alembic/env.py`` never reads the environment
and a failed migration exits non-zero for compose to gate on.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
# The backend package must be importable no matter the caller's cwd.
sys.path.insert(0, str(BACKEND_DIR))


def main() -> None:
    """Upgrade the settings-selected database to the migration head."""

    from alembic import command
    from alembic.config import Config
    from app.core.config import get_settings

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend; ..\.venv\Scripts\python -m pytest tests/test_migrate_script.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Full gates and commit**

Run: `cd backend; ..\.venv\Scripts\ruff check .; ..\.venv\Scripts\ruff format --check .; ..\.venv\Scripts\mypy app tests; ..\.venv\Scripts\python -m pytest`
Expected: all green (the existing stray-`RAG_DATABASE_URL` guard in `tests/test_alembic.py` stays green - the URL flows through explicit code, never the environment in `env.py`).

```bash
git add backend/scripts/migrate.py backend/tests/test_migrate_script.py
git commit -m "feat(backend): add the one-off migration script"
```

### Task 3: The backend image

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`

**Interfaces:**
- Consumes: the installable package `rag-backend` (`pip install .` from `backend/pyproject.toml`).
- Produces: the `rag-backend` image containing `app/`, `alembic/`, `alembic.ini`, `scripts/`, a non-root `appuser`, uvicorn as the default command, and all dependencies in a layer that precedes the source copy. Task 5 builds it once through the `x-backend` anchor.

- [ ] **Step 1: Write the Dockerfile**

`backend/Dockerfile`:

```dockerfile
FROM python:3.14-slim
WORKDIR /app

# Dependencies in their own layer: a code-only rebuild reinstalls nothing. The
# manifest-only dummy build installs the declared dependencies and no packages.
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini ./
COPY scripts/ scripts/
RUN pip install --no-cache-dir --no-deps .

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips=*"]
```

If the manifest-only `pip install .` ever fails to build with zero packages found, replace that single `RUN` with a BuildKit heredoc that parses `project.dependencies` out of `pyproject.toml` with `tomllib` - the two-layer split is the invariant, not the mechanism.

- [ ] **Step 2: Write the .dockerignore**

`backend/.dockerignore`:

```
.venv
.env
__pycache__
.mypy_cache
.pytest_cache
.ruff_cache
tests
*.log
```

- [ ] **Step 3: Build and verify**

Run: `docker build -t rag-backend:plancheck backend`
Expected: build succeeds.

Run: `docker run --rm rag-backend:plancheck python -c "from app.main import app; print(app.title)"`
Expected: `rag-mvp` (the app imports inside the image without touching the database).

Run: `docker run --rm rag-backend:plancheck whoami`
Expected: `appuser`.

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile backend/.dockerignore
git commit -m "build(backend): add the backend image"
```

### Task 4: The web image

**Files:**
- Create: `web/Dockerfile`
- Create: `web/nginx.conf`
- Create: `web/.dockerignore`

**Interfaces:**
- Consumes: Task 1's `/api` surface (the `location /api/` matches it; no build argument - the relative default already lives in `src/app/api.ts`).
- Produces: the `rag-web` image serving the built SPA from the nginx root and proxying `/api/` to the compose `api` service with per-request DNS resolution. Task 5's `web` service builds it.

- [ ] **Step 1: Write the Dockerfile and nginx.conf**

`web/Dockerfile`:

```dockerfile
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
```

`web/nginx.conf`:

```nginx
# Serves the built SPA and reverse-proxies /api to the compose api service.
# No CORS headers anywhere: the compose path is same-origin.
server {
    listen 80;
    # Covers max_upload_mb (25) with headroom; the 1 MB default would reject uploads.
    client_max_body_size 26m;
    # Docker's embedded DNS: re-resolve so a recreated api container is not a dead IP.
    resolver 127.0.0.11 valid=10s;

    location /api/ {
        # The variable forces per-request resolution through the resolver above.
        set $upstream_api http://api:8000;
        # No URI in proxy_pass: the original request URI passes through unchanged,
        # because the backend serves the /api prefix itself.
        proxy_pass $upstream_api;
        # $http_host keeps the :8080 port; $host would drop it.
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        root /usr/share/nginx/html;
        # SPA history-routing fallback.
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 2: Write the .dockerignore**

`web/.dockerignore`:

```
node_modules
dist
test-results
playwright-report
e2e
*.log
```

(`playwright.config.ts` is copied but never compiled: `tsc -b` builds only the tsconfig references, `src/` and `vite.config.ts`.)

- [ ] **Step 3: Build and verify**

Run: `docker build -t rag-web:plancheck web`
Expected: build succeeds.

Run: `docker run --rm rag-web:plancheck nginx -t`
Expected: `syntax is ok` / `test is successful`.

Run: `docker run -d --rm -p 8099:80 --name rag-web-plancheck rag-web:plancheck` then `curl.exe -fsS http://localhost:8099/` and `curl.exe -fsS http://localhost:8099/projects`
Expected: both return the SPA's HTML (the second proves the history fallback). Then `docker stop rag-web-plancheck`.

- [ ] **Step 4: Commit**

```bash
git add web/Dockerfile web/nginx.conf web/.dockerignore
git commit -m "build(web): add the nginx image"
```

### Task 5: The compose stack

**Files:**
- Modify: `deploy/docker-compose.yml` (full rewrite; db/rabbitmq/garage definitions keep their current shape, comments included)
- Create: `deploy/rabbitmq.conf`

**Interfaces:**
- Consumes: Task 2's script (one-off-initialization command), Tasks 3/4's images (via `build`), Task 1's `/api/health` (api healthcheck URL).
- Produces: `docker compose -f deploy/docker-compose.yml up -d` starting the whole system; `-p <scratch>` reuses it with fresh volumes (Task 7). The `x-backend` anchor defines the image once so `--build` cannot produce four divergent builds.

- [ ] **Step 1: Write the compose file**

`deploy/docker-compose.yml`:

```yaml
name: rag

# The single backend image behind the four app services (spec decision 3).
x-backend: &backend
  build: ../backend
  image: rag-backend

services:
  db:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: rag
      POSTGRES_PASSWORD: rag
      POSTGRES_DB: rag
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U rag"]
      interval: 5s
      timeout: 5s
      retries: 10

  rabbitmq:
    image: rabbitmq:3.13-management
    # A stable hostname keeps the broker's data directory usable across recreates:
    # RabbitMQ names its node after the container hostname, and a changed hostname
    # makes it refuse the existing mnesia directory.
    hostname: rabbitmq
    ports:
      - "5672:5672"
      - "15672:15672"
    volumes:
      - rabbitmqdata:/var/lib/rabbitmq
      - ./rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 10s
      retries: 10

  garage:
    image: dxflrs/garage:v2.3.0
    command: /garage server --single-node --default-bucket
    environment:
      GARAGE_DEFAULT_ACCESS_KEY: rag-dev-key
      GARAGE_DEFAULT_SECRET_KEY: rag-dev-secret-local
      GARAGE_DEFAULT_BUCKET: rag-dev
    ports:
      - "3900:3900"
      - "3903:3903"
    volumes:
      - garagemeta:/var/lib/garage/meta
      - garagedata:/var/lib/garage/data
      - ./garage.toml:/etc/garage.toml
    healthcheck:
      test: ["CMD", "/garage", "status"]
      interval: 5s
      timeout: 5s
      retries: 12

  one-off-initialization:
    <<: *backend
    command: ["python", "scripts/migrate.py"]
    # Python registers no SIGTERM handler, and PID 1 ignores unhandled signals:
    # a migration in flight during down would otherwise wait out the stop timeout.
    init: true
    restart: "no"
    environment:
      RAG_DATABASE_URL: postgresql+psycopg://rag:rag@db:5432/rag
    depends_on:
      db:
        condition: service_healthy

  api:
    <<: *backend
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips=*"]
    init: true
    ports:
      - "8000:8000"
    environment:
      RAG_DATABASE_URL: postgresql+psycopg://rag:rag@db:5432/rag
      RAG_BROKER_URL: amqp://guest:guest@rabbitmq:5672//
      RAG_S3_ENDPOINT: http://garage:3900
    depends_on:
      db:
        condition: service_healthy
      one-off-initialization:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 10s
      start_interval: 1s

  worker:
    <<: *backend
    # --concurrency 2: each prefork child holds its own SQLAlchemy pool, and the
    # default (one per CPU in the Docker VM) could crowd the 100-connection
    # Postgres maximum this stack shares with the test suites.
    command: ["celery", "-A", "app.workers.celery_app", "worker", "-Q", "ingestion,embed", "--concurrency", "2"]
    init: true
    environment:
      RAG_DATABASE_URL: postgresql+psycopg://rag:rag@db:5432/rag
      RAG_BROKER_URL: amqp://guest:guest@rabbitmq:5672//
      RAG_S3_ENDPOINT: http://garage:3900
    depends_on:
      db:
        condition: service_healthy
      one-off-initialization:
        condition: service_completed_successfully
      rabbitmq:
        condition: service_healthy

  dispatcher:
    <<: *backend
    command: ["python", "-m", "app.workers.dispatcher"]
    init: true
    environment:
      RAG_DATABASE_URL: postgresql+psycopg://rag:rag@db:5432/rag
      RAG_BROKER_URL: amqp://guest:guest@rabbitmq:5672//
      RAG_S3_ENDPOINT: http://garage:3900
    depends_on:
      db:
        condition: service_healthy
      one-off-initialization:
        condition: service_completed_successfully
      rabbitmq:
        condition: service_healthy

  web:
    build: ../web
    image: rag-web
    ports:
      - "8080:80"
    depends_on:
      api:
        condition: service_healthy

volumes:
  pgdata:
  rabbitmqdata:
  garagemeta:
  garagedata:
```

- [ ] **Step 2: Write the broker conf**

`deploy/rabbitmq.conf`:

```ini
# The app services connect as guest from other containers. The image's bundled
# 10-defaults.conf already allows guest off-loopback; this file pins that posture
# in our tree so an image update cannot silently withdraw it.
loopback_users.guest = false
```

- [ ] **Step 3: Verify the compose graph**

Run: `docker compose -f deploy/docker-compose.yml config --services`
Expected: eight services, one per row of the spec's section 3 table.

Run: `docker compose -f deploy/docker-compose.yml config`
Expected: parses without warnings; the merged `one-off-initialization` block shows the migrate command and `restart: no`; api/worker/dispatcher show `depends_on` with `service_completed_successfully`; the three app services share `image: rag-backend`.

- [ ] **Step 4: Commit**

```bash
git add deploy/docker-compose.yml deploy/rabbitmq.conf
git commit -m "feat(deploy): run the full stack under compose"
```

### Task 6: The runbook

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the Task 5 stack (its commands are the runbook's commands).
- Produces: the single-command runbook Task 7 follows verbatim.

- [ ] **Step 1: Rewrite the runbook sections (spec section 9)**

- Replace "Run the services" with **"Run the whole system"**: `docker compose -f deploy/docker-compose.yml up -d` starts everything; the UI at `http://localhost:8080`, API docs at `http://localhost:8000/api/docs`; `down` stops it; `up -d --build` after code changes recreates the affected services (the dependency layer is cached - section 4.1 of the spec). Keep the existing operational notes under it (the Garage secret warning, the rabbitmq volume note) - they still apply. Add the machine-global note: one system at a time, owned by the checkout that started it; `down` before starting it from another checkout or worktree.
- Remove "Migrate the development database", "Run the API", and "Run the ingestion workers".
- Reword "Setup": the venv now serves the test suites and migrations authoring; `npm install` serves the web toolchain and e2e.
- "Test" unchanged. Keep "Line endings" and "Further reading" as they are.
- Add the one-line dev-server note: `npm run dev` with `VITE_API_BASE_URL=http://localhost:8000/api` still works against the compose API for ad-hoc UI work, but is not the runbook path.

- [ ] **Step 2: Verify against the spec's done-when list**

Read the README top to bottom and check: no native app-tier instructions remain; every command it gives is one this plan exercised (Task 7 runs them); the "Done when" bullets of spec section 13 about the README hold.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: make compose the single runbook path"
```

### Task 7: Packaging smoke and backlog

No product code changes; the only edit is the reverted throwaway comment and the backlog entry. The machine is used exclusively - nothing else may run `up`/`down` on the `rag` project during this task.

**Files:**
- Modify (throwaway, reverted): `backend/app/main.py`
- Modify: `docs/backlog.md`

**Interfaces:**
- Consumes: the Task 5 stack, the Task 6 runbook commands, Tasks 3/4's layer split.
- Produces: the verified "Done when" list of spec section 13, and the backlog entry the spec's section 12 requires.

- [ ] **Step 1: Clear any pre-existing stack**

Run: `docker compose -f deploy/docker-compose.yml down`
Expected: removes whatever old stack held the machine (including the stale worktree-mounted garage from the wild observation in the spec).

- [ ] **Step 2: Boot the whole system from the current tree**

Run: `docker compose -f deploy/docker-compose.yml up -d --build` then `docker compose -f deploy/docker-compose.yml ps`
Expected: all images build; `one-off-initialization` shows `Exited (0)`; api/worker/dispatcher/web `Up`; db/rabbitmq/garage `(healthy)`.

- [ ] **Step 3: Health through both paths**

Run: `curl.exe -fsS http://localhost:8080/api/health` and `curl.exe -fsS http://localhost:8000/api/docs`
Expected: `{"status":"ok"}` through nginx; the docs HTML directly. `curl.exe -fsS http://localhost:8080/` returns the SPA.

- [ ] **Step 4: Journey through the UI**

In a browser at `http://localhost:8080`: register, create a project, upload `backend/tests/fixtures/tiny.pdf`, and watch the row reach **Ready**.
Expected: the run exercises one-off-initialization, api, dispatcher, broker, worker, and Garage in one pass (spec section 8).

- [ ] **Step 5: Upload-limit boundary through the proxy**

PowerShell (the `@file` trick avoids JSON quoting pain):

```powershell
Set-Content "$env:TEMP\reg.json" '{"email":"smoke@example.com","password":"password123"}'
$token = (curl.exe -s -X POST http://localhost:8080/api/auth/register -H "Content-Type: application/json" -d "@$env:TEMP\reg.json" | ConvertFrom-Json).access_token
$auth = "Authorization: Bearer $token"
$ws = (curl.exe -s http://localhost:8080/api/workspaces -H $auth | ConvertFrom-Json)[0].id
$team = (curl.exe -s "http://localhost:8080/api/workspaces/$ws/teams" -H $auth | ConvertFrom-Json)[0].id
Set-Content "$env:TEMP\proj.json" ('{"name":"smoke","team_id":"' + $team + '"}')
$projId = (curl.exe -s -X POST http://localhost:8080/api/projects -H $auth -H "Content-Type: application/json" -d "@$env:TEMP\proj.json" | ConvertFrom-Json).id
[IO.File]::WriteAllBytes("$env:TEMP\over-25m.bin", [byte[]]::new(26738688))   # 25.5 MB
[IO.File]::WriteAllBytes("$env:TEMP\over-27m.bin", [byte[]]::new(28311552))   # 27 MB
curl.exe -s -X POST -H $auth -F "file=@$env:TEMP\over-25m.bin" "http://localhost:8080/api/projects/$projId/uploads"
curl.exe -s -o NUL -w "%{http_code}" -X POST -H $auth -F "file=@$env:TEMP\over-27m.bin" "http://localhost:8080/api/projects/$projId/uploads"
```

Expected: the 25.5 MB upload returns 422 with the backend's copy (`The file is too large. The maximum size is 25 MB.`) - it passed nginx's 26 MB window and hit the app's own check; the 27 MB upload returns 413 (nginx's own refusal).

- [ ] **Step 6: Rebuild speed and nginx re-resolution**

Append a throwaway comment line to `backend/app/main.py`, then `docker compose -f deploy/docker-compose.yml up -d --build`, then `curl.exe -fsS http://localhost:8080/api/health`, then `git restore backend/app/main.py`.
Expected: the build log shows `CACHED` for the dependency layer (`RUN pip install --no-cache-dir .`) and reinstalls only the project; api is recreated; the health check through nginx still answers 200 (the resolver re-resolved the recreated container - a static `proxy_pass` would 502 here). The restore leaves a clean tree.

- [ ] **Step 7: Fresh-volume boot under a scratch project**

Run: `docker compose -f deploy/docker-compose.yml down` (volumes survive), then `docker compose -p rag-smoke -f deploy/docker-compose.yml up -d --build`, then repeat step 3's health checks, then `docker compose -p rag-smoke -f deploy/docker-compose.yml down --volumes`.
Expected: the system boots from nothing with zero manual steps on fresh volumes; the scratch project's volumes are cleaned up.

- [ ] **Step 8: Volumes survived the down; all gates with the system up**

Run: `docker compose -f deploy/docker-compose.yml up -d` (no rebuild), then log `smoke@example.com` in via the UI (the account from step 5 still exists - the named volumes survived), then run every gate: backend `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest`; web `npm run test`, `npm run lint`, `npm run format:check`, `npm run e2e`.
Expected: all green with the full system running - the suites share the infra and nothing collides (8001/5173 vs 8000/8080). The machine is left with the system up, the new normal.

- [ ] **Step 9: Record the backlog entry**

Add to `docs/backlog.md`, under a new timestamped header `## 2026-10-16 - Compose full-stack runtime follow-ups`: the containerized-e2e CI idea from spec section 12 (running the existing journey against a composed stack in CI, where databases are disposable), linking this plan and the feature commits.

```bash
git add docs/backlog.md
git commit -m "docs(backlog): record the containerized-e2e CI idea"
```
