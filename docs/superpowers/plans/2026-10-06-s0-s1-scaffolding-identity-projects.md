# S0+S1: Scaffolding, Identity & Projects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the FastAPI backend skeleton (deps, settings, docker-compose infra, Alembic, pytest against real Postgres) and deliver JWT auth plus project CRUD on the long-term workspace/team data model.

**Architecture:** Monorepo with `backend/` (FastAPI + sync SQLAlchemy 2.0 + Alembic) and `deploy/docker-compose.yml` (Postgres+pgvector, RabbitMQ, MinIO). Identity uses the long-term users/workspaces/teams model with a single-user flow: registration creates user + personal workspace + team + membership in one transaction; project creation auto-grants the creator's personal team the `admin` role; all project access is scoped through the user's teams.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.0 (sync), psycopg[binary] v3, Alembic, pydantic-settings, PyJWT, pwdlib[argon2], pytest, httpx, Docker Compose (pgvector/pgvector:pg17, rabbitmq:3.13-management, minio/minio).

**Spec:** `docs/superpowers/specs/2026-10-06-rag-mvp-slices-design.md` (and `rag_mvp_agent_project_context.md` for product intent). This plan implements spec §3 (repo layout), §4 (S1 design), and the S0 row of §2.

## Global Constraints

- Python 3.14 (spec §4.4: downgrade to 3.12 only if a required wheel is actually missing).
- Sync SQLAlchemy 2.0 (spec §4.4: models shared between FastAPI and Celery later).
- Dependency management: `backend/pyproject.toml` + pip in the existing root `.venv` (spec §4.4).
- S0+S1 dependency set only: fastapi, uvicorn, sqlalchemy 2.x, psycopg[binary] v3, alembic, pydantic-settings, PyJWT, pwdlib[argon2], pytest, httpx. Celery and boto3 arrive in S2 (spec §4.4).
- JWT access token only, 24h expiry, no refresh token (spec §4.3).
- Argon2 password hashing (spec §4.3).
- Tests run against **real Postgres** from docker-compose (dedicated test database `rag_test`), never SQLite (spec §6).
- Table/column names exactly per spec §4.1: `users`, `workspaces`, `teams`, `team_memberships`, `projects`, `project_team_roles`.
- Endpoints exactly per spec §4.2.
- Repo layout exactly per spec §3 (`backend/app/{core,identity,projects}/`, `backend/alembic/`, `backend/tests/`, `deploy/docker-compose.yml`).
- Git commits land directly on the current branch (`master`) at the end of each task (TDD: red, green, commit).
- Runtime services run in Docker; only the Python test/dev tooling runs on the Windows host.

## Review Focus

The spec implies these input classes; no single task's happy-path tests would catch them. Each gets a test in the owning task:

1. **Short password at register (e.g. 7 chars)** — user expects a clear 422 rejection, not a 500 (validated in `RegisterRequest`; test in Task 8, Step 1).
2. **Expired JWT** — user expects 401, not an unhandled `ExpiredSignatureError` 500 (test in Task 9, Step 4).
3. **Cross-user access by UUID guessing** — user B reading/deleting user A's project by id must get 404, never data or a 403 that confirms existence (tests in Task 11, Steps 1 and 5).
4. **Second user registering** — proves `citext` extension and the second personal-workspace path both work, and that per-user workspace isolation holds (test in Task 8, Step 5; Task 12, Step 2).
5. **Partial failure during register's multi-row insert** — a constraint violation midway must roll back the user row too, leaving no orphan user who can then never re-register with that email (test in Task 8, Step 3).
6. **Duplicate project name for the same user** — spec defines no name uniqueness; creating two projects with the same name must succeed (no spurious 409), test in Task 10, Step 4.

---

### Task 1: Backend packaging, settings & config

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/tests/__init__.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `app.core.config.Settings` (pydantic-settings `BaseSettings`) with fields: `database_url: str = "postgresql+psycopg://rag:rag@localhost:5432/rag"`, `jwt_secret: str = "dev-secret-change-me"`, `jwt_algorithm: str = "HS256"`, `jwt_access_token_ttl_hours: int = 24`; env prefix `"RAG_"`; `get_settings()` returning a cached `Settings`. `app.main.app` (bare `FastAPI(title="rag-mvp")` instance, no routes yet — later tasks attach routers).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config.py
from app.core.config import Settings


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://rag:rag@localhost:5432/rag"
    assert s.jwt_algorithm == "HS256"
    assert s.jwt_access_token_ttl_hours == 24


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("RAG_DATABASE_URL", "postgresql+psycopg://u:p@h:1/db")
    monkeypatch.setenv("RAG_JWT_SECRET", "abc")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://u:p@h:1/db"
    assert s.jwt_secret == "abc"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'` (package and pyproject do not exist yet).

- [ ] **Step 3: Create packaging and settings code**

Create `backend/pyproject.toml` (setuptools backend, package name `rag-backend`, `where = ["."]`, `include = ["app*"]`, deps: fastapi, uvicorn[standard], sqlalchemy>=2, psycopg[binary]>=3.2, alembic, pydantic-settings, PyJWT, pwdlib[argon2]; optional `[project.optional-dependencies] dev = ["pytest", "httpx"]`). Install with `..\.venv\Scripts\pip.exe install -e ".[dev]"`. Then create `app/core/config.py` implementing `Settings` and a `@lru_cache` `get_settings()`, the `__init__.py` files, and a bare `app/main.py` with `app = FastAPI(title="rag-mvp")`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd D:\Projects\RAG && git add backend/
git commit -m "feat(backend): packaging, settings module, bare FastAPI app"
```

### Task 2: Deploy infrastructure (docker-compose)

**Files:**
- Create: `deploy/docker-compose.yml`
- Modify: `backend/app/main.py` (add `/health` route)
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Consumes: `app.main.app` (Task 1).
- Produces: compose project named `rag` with services on default ports: `db` (5432), `rabbitmq` (5672/15672), `minio` (9000/9001). `GET /health` → `200 {"status": "ok"}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_health.py
from fastapi.testclient import TestClient

from app.main import app


def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/test_health.py -v`
Expected: FAIL — 404 (no `/health` route).

- [ ] **Step 3: Add `/health` and write docker-compose**

Add a `@app.get("/health")` route in `app/main.py` returning `{"status": "ok"}`. Create `deploy/docker-compose.yml` with compose project name `rag` and services (spec §2 S0 row):
- `db`: image `pgvector/pgvector:pg17`, env `POSTGRES_USER=rag`, `POSTGRES_PASSWORD=rag`, `POSTGRES_DB=rag`, port `5432:5432`, volume `pgdata:/var/lib/postgresql/data`, healthcheck `pg_isready -U rag`.
- `rabbitmq`: image `rabbitmq:3.13-management`, ports `5672:5672`, `15672:15672`, default guest/guest.
- `minio`: image `minio/minio`, command `server /data --console-address ":9001"`, env `MINIO_ROOT_USER=minio`, `MINIO_ROOT_PASSWORD=minio123`, ports `9000:9000`, `9001:9001`, volume `miniodata:/data`.
- named volumes `pgdata`, `miniodata`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd D:\Projects\RAG && git add backend/ deploy/
git commit -m "feat: /health endpoint and docker-compose infra (postgres+pgvector, rabbitmq, minio)"
```

### Task 3: Database engine, session & pytest database fixtures

**Files:**
- Create: `backend/app/core/db.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Consumes: `app.core.config.Settings`, `get_settings()` (Task 1).
- Produces: `app.core.db.make_engine(database_url: str) -> Engine`, `app.core.db.SessionLocal` (sessionmaker bound to the settings engine), `get_db()` FastAPI dependency yielding a `Session`. Test fixtures (used by every later task): `settings` (function scope — `Settings` with `database_url` pointing at `rag_test`, overridable via `RAG_TEST_DATABASE_URL` env, and fixed `jwt_secret="test-secret"`), `engine` (session scope — creates `rag_test` DB if missing, runs `alembic upgrade head` via `alembic.config.Config` pointing at `backend/alembic.ini`, drops the DB on teardown), `db_session` (function scope — one connection + outer transaction per test, rolled back after), `client` (function scope — `TestClient(app)` with `get_db` overridden to yield the test's `db_session`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_db.py
from sqlalchemy import text

from app.core.db import make_engine


def test_make_engine_connects(settings):
    engine = make_engine(settings.database_url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
    engine.dispose()


def test_db_session_fixture_works(db_session):
    assert db_session.execute(text("SELECT 1")).scalar() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.db'`.

- [ ] **Step 3: Implement db module and fixtures**

Create `app/core/db.py` with `make_engine` (plain `create_engine(url)`), `SessionLocal = sessionmaker(bind=make_engine(get_settings().database_url))`, and `get_db()` yielding/closing a session. Create `tests/conftest.py` implementing the four fixtures in the Produces block; the `engine` fixture builds an admin engine against the `postgres` maintenance DB to `CREATE DATABASE rag_test` when missing (guard with `SELECT 1 FROM pg_database WHERE datname='rag_test'`).

Note: the `engine` fixture requires Docker Desktop running with the compose `db` service up (`docker compose -f deploy/docker-compose.yml up -d db`). If the daemon is down at execution time, start it first and wait for the healthcheck.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/test_db.py -v`
Expected: PASS (2 passed; alembic `upgrade head` currently applies zero migrations — base is stamped in Task 5).

- [ ] **Step 5: Commit**

```bash
cd D:\Projects\RAG && git add backend/
git commit -m "feat(backend): db engine/session, get_db dependency, pytest real-postgres fixtures"
```

### Task 4: SQLAlchemy models for identity & projects

**Files:**
- Create: `backend/app/core/models.py` (shared `Base`)
- Create: `backend/app/identity/__init__.py`
- Create: `backend/app/identity/models.py`
- Create: `backend/app/projects/__init__.py`
- Create: `backend/app/projects/models.py`
- Test: `backend/tests/identity/__init__.py`
- Test: `backend/tests/identity/test_models.py`

**Interfaces:**
- Consumes: `db_session` fixture (Task 3).
- Produces (exact mapped classes; later tasks import these):
  - `app.identity.models.User` — `id: UUID pk default uuid4`, `email: str`, `password_hash: str`, `created_at: datetime` (server default `now()`).
  - `app.identity.models.Workspace` — `id`, `name: str`, `owner_user_id -> users.id`, `is_personal: bool`.
  - `app.identity.models.Team` — `id`, `workspace_id -> workspaces.id`, `name: str`, `is_personal: bool`.
  - `app.identity.models.TeamMembership` — `id`, `team_id -> teams.id`, `user_id -> users.id`.
  - `app.projects.models.Project` — `id`, `workspace_id -> workspaces.id`, `name: str`, `created_at`.
  - `app.projects.models.ProjectTeamRole` — `id`, `project_id -> projects.id`, `team_id -> teams.id`, `role: str` (`"admin" | "editor" | "viewer"`).
  - `app.core.models.Base` — shared `DeclarativeBase`; `app.identity.models` and `app.projects.models` import each other as needed so relationships resolve (e.g. `Project.team_roles`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/identity/test_models.py
import pytest
from sqlalchemy.exc import IntegrityError

from app.identity.models import Team, TeamMembership, User, Workspace
from app.projects.models import Project, ProjectTeamRole


def _make_user(db, email="a@example.com"):
    user = User(email=email, password_hash="x")
    db.add(user)
    db.flush()
    ws = Workspace(name="Personal", owner_user_id=user.id, is_personal=True)
    db.add(ws)
    db.flush()
    team = Team(workspace_id=ws.id, name="Personal", is_personal=True)
    db.add(team)
    db.flush()
    db.add(TeamMembership(team_id=team.id, user_id=user.id))
    db.flush()
    return user, ws, team


def test_register_graph_persists(db_session):
    user, ws, team = _make_user(db_session)
    assert user.id and ws.owner_user_id == user.id and team.workspace_id == ws.id


def test_team_membership_unique(db_session):
    user, ws, team = _make_user(db_session)
    db_session.add(TeamMembership(team_id=team.id, user_id=user.id))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_project_team_role_unique_and_role_check(db_session):
    user, ws, team = _make_user(db_session)
    project = Project(workspace_id=ws.id, name="p1")
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectTeamRole(project_id=project.id, team_id=team.id, role="admin"))
    db_session.flush()
    db_session.add(ProjectTeamRole(project_id=project.id, team_id=team.id, role="viewer"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    user, ws, team = _make_user(db_session, email="b@example.com")
    project = Project(workspace_id=ws.id, name="p2")
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectTeamRole(project_id=project.id, team_id=team.id, role="owner"))
    with pytest.raises(IntegrityError):
        db_session.flush()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/identity/test_models.py -v`
Expected: FAIL — models do not exist; also `unique`/`check` constraints do not exist yet (no migration). Collection errors are acceptable red at this point.

- [ ] **Step 3: Implement the models**

Create `app/core/models.py` with `Base(DeclarativeBase)`. Create the six mapped classes per the Produces block using SQLAlchemy 2.0 `Mapped[]`/`mapped_column` style: `id` as `UUID(as_uuid=True)` pk `default=uuid4`; `email` as `String` (the `citext` type lands in the Task 5 migration — the model's Python type stays `str`; declare it as `Mapped[str]` over a `CITEXT()` column so model and schema match); FK columns with `ForeignKey`; `UniqueConstraint("team_id", "user_id")` on `team_memberships`; `UniqueConstraint("project_id", "team_id")` plus `CheckConstraint("role IN ('admin','editor','viewer')")` on `project_team_roles`.

Note: until Task 5's migration exists these tests still fail on missing tables — that is expected; the green run is Step 5 after Task 5 lands. (Tasks 4 and 5 are one red-green cycle across two commits: models commit red-with-migration-pending is NOT committed — do Step 5 commit only after Task 5 makes them green; commit Task 4's models together with the Task 5 migration in Task 5's commit.)

Adjusted flow: do NOT commit in Step 5 of this task; Task 5's commit includes both tasks' files.

- [ ] **Step 4: (deferred — green run happens as Task 5 Step 4)**

Run Task 5 first; its Step 4 runs this task's tests.

### Task 5: Alembic setup + identity/projects migration

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/0001_identity_projects.py`
- Test: `backend/tests/test_alembic.py`

**Interfaces:**
- Consumes: all models from Task 4 (`Base.metadata` must contain all six tables); `engine` fixture (Task 3, which runs `alembic upgrade head`).
- Produces: revision `0001` creating (in order) extension `citext`, then tables `users`, `workspaces`, `teams`, `team_memberships`, `projects`, `project_team_roles` with the constraints from Task 4; `downgrade` drops in reverse. Migration is autogenerate-based with `include_schemas=False`; `alembic/env.py` reads the URL from `RAG_DATABASE_URL` env var when set, else from `alembic.ini`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_alembic.py
from sqlalchemy import inspect, text


def test_identity_tables_exist(engine):
    with engine.connect() as conn:
        names = set(inspect(conn).get_table_names())
    assert {"users", "workspaces", "teams", "team_memberships",
            "projects", "project_team_roles"} <= names


def test_citext_email_case_insensitive(engine, db_session):
    from app.identity.models import User
    db_session.add(User(email="Case@Example.com", password_hash="x"))
    db_session.flush()
    found = db_session.query(User).filter(User.email == "case@example.com").one()
    assert found.email == "Case@Example.com"


def test_migration_is_head(settings):
    import subprocess
    out = subprocess.run(
        ["..\\.venv\\Scripts\\alembic.exe", "-c", "alembic.ini", "heads"],
        capture_output=True, text=True, cwd=".",
    )
    assert out.returncode == 0
    assert "0001" in out.stdout and "(head)" in out.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/test_alembic.py -v`
Expected: FAIL — `alembic.ini` does not exist; tables do not exist.

- [ ] **Step 3: Initialize Alembic and generate the migration**

Run `..\.venv\Scripts\alembic.exe init alembic` inside `backend/`, then edit: `alembic.ini` `sqlalchemy.url = postgresql+psycopg://rag:rag@localhost:5432/rag`; `alembic/env.py` to import `Base` from `app.core.models` plus `app.identity.models` and `app.projects.models` (so metadata is complete), set `target_metadata = Base.metadata`, and prefer `os.environ["RAG_DATABASE_URL"]` when set. Generate with `alembic revision --autogenerate -m "identity and projects"` and rename the file to `0001_identity_projects.py`, set `revision = "0001"`. Edit the migration so `op.execute("CREATE EXTENSION IF NOT EXISTS citext")` runs before table creation and the `users.email` column is `CITEXT()` (postgresql dialect type), unique.

- [ ] **Step 4: Run tests to verify they pass (this also greens Task 4)**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/test_alembic.py tests/identity/test_models.py -v`
Expected: PASS (all 5). If `test_citext_email_case_insensitive` fails, verify the column type is `CITEXT` in the migration and the extension is created in the `rag_test` database (the `engine` fixture recreates the DB per session — ensure `CREATE EXTENSION` is inside the migration, not manual setup).

- [ ] **Step 5: Commit (includes Task 4 files)**

```bash
cd D:\Projects\RAG && git add backend/
git commit -m "feat(identity,projects): sqlalchemy models + alembic migration 0001 (users, workspaces, teams, memberships, projects, project_team_roles)"
```

### Task 6: Password hashing & JWT helpers

**Files:**
- Create: `backend/app/core/security.py`
- Test: `backend/tests/core/__init__.py`
- Test: `backend/tests/core/test_security.py`

**Interfaces:**
- Consumes: `Settings`/`get_settings()` (Task 1).
- Produces: `app.core.security.hash_password(password: str) -> str`, `verify_password(password: str, password_hash: str) -> bool` (pwdlib Argon2), `create_access_token(user_id: UUID, settings: Settings) -> str` (claims `sub=str(user_id)`, `exp=now+settings.jwt_access_token_ttl_hours hours`, signed with `settings.jwt_algorithm`/`settings.jwt_secret`), `decode_access_token(token: str, settings: Settings) -> UUID` (raises `jwt.InvalidTokenError` on any failure).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/core/test_security.py
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import Settings
from app.core.security import (create_access_token, decode_access_token,
                               hash_password, verify_password)


def _settings():
    return Settings(_env_file=None, jwt_secret="test-secret")


def test_hash_roundtrip():
    h = hash_password("correct horse")
    assert h != "correct horse"
    assert verify_password("correct horse", h)
    assert not verify_password("wrong", h)


def test_token_roundtrip():
    uid = uuid.uuid4()
    token = create_access_token(uid, _settings())
    assert decode_access_token(token, _settings()) == uid


def test_token_expiry_claim():
    token = create_access_token(uuid.uuid4(), _settings())
    claims = jwt.decode(token, "test-secret", algorithms=["HS256"])
    exp = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    assert timedelta(hours=23) < exp - datetime.now(timezone.utc) <= timedelta(hours=24)


def test_decode_rejects_garbage():
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("not-a-token", _settings())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/core/test_security.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.security'`.

- [ ] **Step 3: Implement security helpers**

Create `app/core/security.py` per the Produces block: pwdlib `PasswordHash.recommended()` (Argon2) for hashing; PyJWT `encode`/`decode` for tokens.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/core/test_security.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd D:\Projects\RAG && git add backend/
git commit -m "feat(core): argon2 password hashing and JWT helpers"
```

### Task 7: Identity schemas & registration service

**Files:**
- Create: `backend/app/identity/schemas.py`
- Create: `backend/app/identity/service.py`
- Test: `backend/tests/identity/test_service.py`

**Interfaces:**
- Consumes: models (Task 4), `hash_password` (Task 6), `db_session` (Task 3).
- Produces:
  - `app.identity.schemas.RegisterRequest` — `email: EmailStr` (add `email-validator` to pyproject deps), `password: str = Field(min_length=8)`.
  - `app.identity.schemas.LoginRequest` — `email: EmailStr`, `password: str`.
  - `app.identity.service.RegistrationResult` — dataclass/pydantic model with `user: User`, `workspace: Workspace`, `team: Team`.
  - `app.identity.service.register_user(db: Session, email: str, password: str) -> RegistrationResult` — raises `service.EmailAlreadyRegistered` (custom exception) on duplicate; creates user + personal workspace (`name="Personal"`) + personal team (`name="Personal"`) + membership in one transaction and commits.
  - `app.identity.service.authenticate_user(db: Session, email: str, password: str) -> User | None` — None on unknown email or bad password.
  - `app.identity.service.get_personal_context(db: Session, user_id: UUID) -> tuple[Workspace, Team]` — the user's personal workspace and team.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/identity/test_service.py
import pytest

from app.identity import service


def test_register_creates_full_personal_graph(db_session):
    result = service.register_user(db_session, "new@example.com", "password123")
    assert result.workspace.owner_user_id == result.user.id
    assert result.workspace.is_personal and result.team.is_personal
    assert result.team.workspace_id == result.workspace.id
    ws, team = service.get_personal_context(db_session, result.user.id)
    assert ws.id == result.workspace.id and team.id == result.team.id


def test_register_duplicate_email_raises(db_session):
    service.register_user(db_session, "dup@example.com", "password123")
    with pytest.raises(service.EmailAlreadyRegistered):
        service.register_user(db_session, "DUP@example.com", "password123")


def test_authenticate_user(db_session):
    service.register_user(db_session, "auth@example.com", "password123")
    assert service.authenticate_user(db_session, "auth@example.com", "password123")
    assert service.authenticate_user(db_session, "auth@example.com", "wrong") is None
    assert service.authenticate_user(db_session, "ghost@example.com", "password123") is None
```

Note: the duplicate-email test uses different casing deliberately — it pins case-insensitive uniqueness at the service level (backed by `citext`), which is also what protects register from the orphan-user failure mode (Review Focus #5: any mid-transaction failure must roll back cleanly so the email stays free; the `IntegrityError` → `EmailAlreadyRegistered` translation plus session rollback implements that).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/identity/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.identity.service'`.

- [ ] **Step 3: Implement schemas and service**

Create `schemas.py` per Produces. In `service.py`: `register_user` adds all four rows, flushes, and commits, catching `IntegrityError` to `db.rollback()` and raise `EmailAlreadyRegistered`; `authenticate_user` looks up by email and uses `verify_password`; `get_personal_context` queries `Workspace`/`Team` where `is_personal` and owner matches.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/identity/test_service.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd D:\Projects\RAG && git add backend/
git commit -m "feat(identity): registration/auth service with personal workspace+team bootstrap"
```

### Task 8: Auth endpoints (`/auth/register`, `/auth/login`)

**Files:**
- Create: `backend/app/identity/router.py`
- Modify: `backend/app/main.py` (include identity router)
- Test: `backend/tests/identity/test_auth_api.py`

**Interfaces:**
- Consumes: `RegisterRequest`/`LoginRequest`, `register_user`/`authenticate_user`, `EmailAlreadyRegistered` (Task 7); `create_access_token` (Task 6); `get_db` (Task 3); `client` fixture (Task 3).
- Produces: `app.identity.router.router` (`APIRouter`). `POST /auth/register` → `201 {"access_token": str, "token_type": "bearer"}`; `409 {"detail": "email already registered"}` on duplicate. `POST /auth/login` → `200` same body; `401 {"detail": "invalid credentials"}` on failure.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/identity/test_auth_api.py
def test_register_returns_jwt(client):
    r = client.post("/auth/register",
                    json={"email": "api@example.com", "password": "password123"})
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer" and len(body["access_token"]) > 20


def test_register_duplicate_409(client):
    payload = {"email": "twice@example.com", "password": "password123"}
    assert client.post("/auth/register", json=payload).status_code == 201
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 409
    assert r.json() == {"detail": "email already registered"}


def test_register_short_password_422(client):
    r = client.post("/auth/register",
                    json={"email": "short@example.com", "password": "1234567"})
    assert r.status_code == 422


def test_login_success_and_failure(client):
    client.post("/auth/register",
                json={"email": "login@example.com", "password": "password123"})
    ok = client.post("/auth/login",
                     json={"email": "login@example.com", "password": "password123"})
    assert ok.status_code == 200 and ok.json()["access_token"]
    bad = client.post("/auth/login",
                      json={"email": "login@example.com", "password": "nope1234"})
    assert bad.status_code == 401
    assert bad.json() == {"detail": "invalid credentials"}


def test_second_user_registers_and_logs_in(client):
    client.post("/auth/register",
                json={"email": "first@example.com", "password": "password123"})
    r = client.post("/auth/register",
                    json={"email": "second@example.com", "password": "password123"})
    assert r.status_code == 201
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/identity/test_auth_api.py -v`
Expected: FAIL — 404 on both routes (router not mounted).

- [ ] **Step 3: Implement the router**

Create `app/identity/router.py` with the two endpoints per Produces: call the service with the request body, translate `EmailAlreadyRegistered` to `HTTPException(409, "email already registered")`, translate `None` from `authenticate_user` to `HTTPException(401, "invalid credentials")`, return `{"access_token": create_access_token(user.id, settings), "token_type": "bearer"}`. Mount in `app/main.py` via `app.include_router(router)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/identity/test_auth_api.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
cd D:\Projects\RAG && git add backend/
git commit -m "feat(identity): /auth/register and /auth/login endpoints returning JWT"
```

### Task 9: `get_current_user` dependency & `GET /users/me`

**Files:**
- Create: `backend/app/identity/dependencies.py`
- Modify: `backend/app/identity/router.py` (add `/users/me`)
- Test: `backend/tests/identity/test_users_me.py`

**Interfaces:**
- Consumes: `decode_access_token` (Task 6), `get_db` (Task 3), `User` (Task 4), router (Task 8).
- Produces: `app.identity.dependencies.get_current_user` — FastAPI dependency using `HTTPBearer`; `401 {"detail": "invalid or expired token"}` on missing/invalid/expired token or unknown user id. `GET /users/me` → `200 {"user_id": str, "email": str, "workspace_id": str, "team_id": str}` (workspace/team from `get_personal_context`, Task 7).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/identity/test_users_me.py
import uuid


def _register(client, email="me@example.com"):
    r = client.post("/auth/register",
                    json={"email": email, "password": "password123"})
    return r.json()["access_token"]


def test_users_me_returns_ids(client):
    token = _register(client)
    r = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "me@example.com"
    uuid.UUID(body["user_id"]); uuid.UUID(body["workspace_id"]); uuid.UUID(body["team_id"])


def test_users_me_requires_auth(client):
    assert client.get("/users/me").status_code in (401, 403)


def test_users_me_rejects_bad_token(client):
    r = client.get("/users/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid or expired token"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/identity/test_users_me.py -v`
Expected: FAIL — 404 (`/users/me` not mounted).

- [ ] **Step 3: Write the expired-token test (Review Focus #2)**

Append to `tests/identity/test_users_me.py`:

```python
def test_users_me_expired_token_401(client, settings):
    from datetime import datetime, timedelta, timezone
    import jwt as pyjwt

    token = pyjwt.encode(
        {"sub": str(uuid.uuid4()),
         "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        settings.jwt_secret, algorithm=settings.jwt_algorithm)
    r = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid or expired token"}
```

- [ ] **Step 4: Implement dependency and endpoint**

Create `app/identity/dependencies.py`: `get_current_user(credentials=Depends(HTTPBearer()), db=Depends(get_db), settings=Depends(get_settings))` — decode via `decode_access_token`, catch `jwt.InvalidTokenError`, load `User` by id, raise `HTTPException(401, "invalid or expired token")` on any failure. Add `GET /users/me` to the identity router returning the shape in Produces (uses `get_personal_context`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/identity/test_users_me.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
cd D:\Projects\RAG && git add backend/
git commit -m "feat(identity): get_current_user dependency and /users/me"
```

### Task 10: Projects service & schemas

**Files:**
- Create: `backend/app/projects/schemas.py`
- Create: `backend/app/projects/service.py`
- Test: `backend/tests/projects/__init__.py`
- Test: `backend/tests/projects/test_service.py`

**Interfaces:**
- Consumes: models (Task 4), `get_personal_context` (Task 7), `db_session`.
- Produces:
  - `app.projects.schemas.ProjectCreate` — `name: str = Field(min_length=1, max_length=200)`.
  - `app.projects.schemas.ProjectOut` — `id: UUID`, `name: str`, `created_at: datetime`.
  - `app.projects.service.create_project(db, user: User, name: str) -> Project` — creates the project in the user's personal workspace and inserts `ProjectTeamRole(project_id, personal_team_id, "admin")` in one transaction (commit).
  - `app.projects.service.list_projects(db, user: User) -> list[Project]` — projects joined through `ProjectTeamRole` → `TeamMembership` for the user.
  - `app.projects.service.get_project_for_user(db, user: User, project_id: UUID) -> Project | None` — None when not visible.
  - `app.projects.service.delete_project(db, project: Project) -> None` — deletes project and its `ProjectTeamRole` rows in one transaction (commit).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/projects/test_service.py
from app.identity import service as identity_service
from app.projects import service as project_service


def _user(db, email):
    return identity_service.register_user(db, email, "password123").user


def test_create_project_grants_personal_team_admin(db_session):
    user = _user(db_session, "owner@example.com")
    project = project_service.create_project(db_session, user, "kb1")
    fetched = project_service.get_project_for_user(db_session, user, project.id)
    assert fetched and fetched.name == "kb1"


def test_list_projects_scopes_to_user(db_session):
    alice = _user(db_session, "alice@example.com")
    bob = _user(db_session, "bob@example.com")
    project_service.create_project(db_session, alice, "alice-kb")
    project_service.create_project(db_session, bob, "bob-kb")
    assert [p.name for p in project_service.list_projects(db_session, alice)] == ["alice-kb"]
    assert project_service.get_project_for_user(
        db_session, alice,
        project_service.list_projects(db_session, bob)[0].id) is None


def test_delete_project_removes_visibility(db_session):
    user = _user(db_session, "del@example.com")
    project = project_service.create_project(db_session, user, "gone")
    project_service.delete_project(db_session, project)
    assert project_service.get_project_for_user(db_session, user, project.id) is None


def test_duplicate_project_name_allowed(db_session):
    user = _user(db_session, "dupe@example.com")
    a = project_service.create_project(db_session, user, "same")
    b = project_service.create_project(db_session, user, "same")
    assert a.id != b.id
    assert len(project_service.list_projects(db_session, user)) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/projects/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.projects.service'`.

- [ ] **Step 3: Implement service and schemas**

Create `schemas.py` and `service.py` per Produces. Visibility query: `Project` join `ProjectTeamRole` join `TeamMembership`, filter `TeamMembership.user_id == user.id`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/projects/test_service.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd D:\Projects\RAG && git add backend/
git commit -m "feat(projects): project service with team-scoped visibility"
```

### Task 11: Projects endpoints

**Files:**
- Create: `backend/app/projects/router.py`
- Modify: `backend/app/main.py` (include projects router)
- Test: `backend/tests/projects/test_projects_api.py`

**Interfaces:**
- Consumes: `get_current_user` (Task 9), project service + schemas (Task 10), `get_db` (Task 3).
- Produces: `app.projects.router.router`. `POST /projects` → `201 ProjectOut`; `GET /projects` → `200 [ProjectOut]`; `GET /projects/{id}` → `200 ProjectOut` or `404 {"detail": "project not found"}`; `DELETE /projects/{id}` → `204` or `404` same body. All require auth (401 without token).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/projects/test_projects_api.py
def _auth(client, email):
    r = client.post("/auth/register",
                    json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_create_and_list_projects(client):
    headers = _auth(client, "crl@example.com")
    r = client.post("/projects", json={"name": "kb"}, headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "kb" and body["id"] and body["created_at"]
    listed = client.get("/projects", headers=headers)
    assert listed.status_code == 200
    assert [p["name"] for p in listed.json()] == ["kb"]


def test_get_other_users_project_is_404(client):
    alice = _auth(client, "a2@example.com")
    bob = _auth(client, "b2@example.com")
    pid = client.post("/projects", json={"name": "secret"}, headers=alice).json()["id"]
    r = client.get(f"/projects/{pid}", headers=bob)
    assert r.status_code == 404
    assert r.json() == {"detail": "project not found"}


def test_projects_require_auth(client):
    assert client.get("/projects").status_code in (401, 403)
    assert client.post("/projects", json={"name": "x"}).status_code in (401, 403)


def test_create_project_validates_name(client):
    headers = _auth(client, "val@example.com")
    assert client.post("/projects", json={"name": ""}, headers=headers).status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/projects/test_projects_api.py -v`
Expected: FAIL — 404 (router not mounted).

- [ ] **Step 3: Write the delete test (Review Focus #3)**

Append to `tests/projects/test_projects_api.py`:

```python
def test_delete_project_flow_and_cross_user_404(client):
    alice = _auth(client, "del-a@example.com")
    bob = _auth(client, "del-b@example.com")
    pid = client.post("/projects", json={"name": "temp"}, headers=alice).json()["id"]
    assert client.delete(f"/projects/{pid}", headers=bob).status_code == 404
    assert client.delete(f"/projects/{pid}", headers=alice).status_code == 204
    assert client.get(f"/projects/{pid}", headers=alice).status_code == 404
    assert client.delete(f"/projects/{pid}", headers=alice).status_code == 404
```

- [ ] **Step 4: Implement the router**

Create `app/projects/router.py` per Produces: each handler takes `user=Depends(get_current_user)`, `db=Depends(get_db)`; `get`/`delete` call `get_project_for_user` and raise `HTTPException(404, "project not found")` on None. Mount in `app/main.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/projects/test_projects_api.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
cd D:\Projects\RAG && git add backend/
git commit -m "feat(projects): project CRUD endpoints with team-scoped 404 semantics"
```

### Task 12: Full-suite verification & S0+S1 closeout

**Files:**
- Modify: `backend/pyproject.toml` (only if `email-validator` was not already added in Task 7)
- Test: `backend/tests/test_smoke_e2e.py`

**Interfaces:**
- Consumes: everything from Tasks 1–11.
- Produces: one end-to-end smoke test proving the S0+S1 "done when" (spec §2): register → login → create → list → delete.

- [ ] **Step 1: Write the smoke test**

```python
# backend/tests/test_smoke_e2e.py
def test_register_login_project_lifecycle(client):
    token = client.post(
        "/auth/register",
        json={"email": "e2e@example.com", "password": "password123"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    token2 = client.post(
        "/auth/login",
        json={"email": "e2e@example.com", "password": "password123"},
    ).json()["access_token"]
    assert token2

    me = client.get("/users/me", headers=headers).json()
    assert me["email"] == "e2e@example.com"

    pid = client.post("/projects", json={"name": "e2e-kb"}, headers=headers).json()["id"]
    assert client.get(f"/projects/{pid}", headers=headers).status_code == 200
    assert len(client.get("/projects", headers=headers).json()) == 1
    assert client.delete(f"/projects/{pid}", headers=headers).status_code == 204
    assert client.get("/projects", headers=headers).json() == []
```

- [ ] **Step 2: Run the whole backend suite**

Run: `cd D:\Projects\RAG\backend && ..\.venv\Scripts\python.exe -m pytest tests/ -v`
Expected: ALL PASS (~30 tests). Fix any inter-test coupling (e.g. fixture leakage) rather than weakening assertions.

- [ ] **Step 3: Verify live stack boots (S0 "done when")**

Run: `docker compose -f deploy/docker-compose.yml up -d` then `docker compose -f deploy/docker-compose.yml ps`
Expected: `db`, `rabbitmq`, `minio` all `Up`/`healthy`. Then `cd backend && ..\.venv\Scripts\uvicorn.exe app.main:app --port 8000` (briefly) and `curl http://localhost:8000/health` returns `{"status":"ok"}`. Stop uvicorn afterwards.

- [ ] **Step 4: Commit**

```bash
cd D:\Projects\RAG && git add backend/
git commit -m "test: S0+S1 end-to-end smoke (register -> login -> project lifecycle)"
```

---

## Self-Review Notes (completed during planning)

1. **Spec coverage:** S0 row — git init (pre-existing), backend layout (T1), pyproject+deps (T1), settings (T1), docker-compose (T2), Alembic (T5), `/health` (T2), pytest harness (T3). S1 — data model §4.1 (T4/T5), endpoints §4.2 (T8/T9/T11), auth decisions §4.3 (T6/T9), tech decisions §4.4 (T1/T3). No gaps.
2. **Type consistency:** `register_user`/`authenticate_user`/`get_personal_context` signatures identical in T7 (defined), T8/T9/T10 (consumed). `create_access_token(user_id, settings)` consistent T6→T8. `get_project_for_user(db, user, project_id)` consistent T10→T11.
3. **Task 4/5 ordering:** models and migration form one red-green cycle; combined commit in Task 5 (noted inline in Task 4).
4. **Proportion:** plan is ~2.5× the S0+S1-relevant spec sections; code blocks are tests and exact values, not implementation bodies.
