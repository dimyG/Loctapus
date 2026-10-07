# Review Feedback: Identity & Projects Revisions - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address 5 review comments on the S0+S1 delivery: add logout with real token revocation, move `is_personal` off Workspace/Team onto a `Project.is_public` visibility flag, add ORM relationships, auto-create a default project at registration, and scope project creation to an explicit `team_id` with workspace/team discovery endpoints.

**Architecture:** Keep the two-module split (`identity/` = users/auth/workspaces/teams, `projects/` = project domain) per the user's explicit ruling. Registration becomes a single atomic transaction creating the user, default workspace/team/membership, and a default project. Project creation moves from "always the user's personal team" to "an explicit `team_id` the user must belong to". Visibility splits into team-scoped (unchanged) and public (`Project.is_public`, viewable by any authenticated user, never editable/deletable by non-members).

**Tech Stack:** FastAPI, sync SQLAlchemy 2.0, Alembic, PyJWT, pwdlib[argon2], pytest against real Postgres (docker-compose `rag_test`).

**Spec:** `docs/superpowers/specs/2026-10-06-rag-mvp-slices-design.md` (updated by Task 7 to match this plan).

## Global Constraints

- Python 3.14, sync SQLAlchemy 2.0 (no async sessions).
- Tests run against real Postgres only (never SQLite), via the existing `tests/conftest.py` harness (per-test transaction rollback).
- TDD: every behavior task writes the failing test first (RED), then implements (GREEN).
- Authz pattern: never leak resource existence. Inaccessible and nonexistent resources both return `404` with a neutral message (existing pattern in `projects/router.py`).
- JWT: HS256, 24h expiry, `sub` claim = user id. This plan adds a `jti` claim (uuid4) for revocation.
- Every Alembic migration gets a working `downgrade()`.
- No em dashes in any written artifact (code comments, docs, commit messages).

## Review Focus

1. `POST /projects` with a `team_id` the caller does not belong to must not create the project (404). Missing membership validation = any user can create projects in any team.
2. A public project (`is_public=True`) must be viewable but NOT editable or deletable by non-members. `PATCH`/`DELETE` must still require team `admin` role regardless of `is_public`.
3. A revoked token must be rejected by every authenticated endpoint (enforced centrally in `get_current_user`), not only blocked at the logout endpoint itself.
4. `register_user` must be one atomic transaction: if default-project creation fails, the user/workspace/team rows must roll back too.
5. Two logins for the same user must produce distinct `jti`s: logging out one session must not invalidate the other.

---

### Task 1: Schema foundation - models, relationships, migration

**Files:**
- Modify: `backend/app/identity/models.py`
- Modify: `backend/app/projects/models.py`
- Modify: `backend/app/identity/service.py` (minimal: drop `is_personal` constructor args and filter usage - see Ruling 4 in the SDD ledger)
- Create: `backend/alembic/versions/0002_review_fixes.py`
- Test: `backend/tests/identity/test_models.py`, `backend/tests/test_alembic.py`, `backend/tests/identity/test_service.py` (drop one `is_personal` assertion)

**Interfaces:**
- Consumes: existing `Base` (`app/core/models.py`), existing table names/FKs.
- Produces:
  - `app.identity.models.RevokedToken` - `jti: str` (pk), `expires_at: datetime`, `revoked_at: datetime`.
  - `Workspace.is_personal` and `Team.is_personal` removed.
  - `Project.is_public: bool` (default `False`).
  - Relationships (all `back_populates` pairs): `User.owned_workspaces`/`Workspace.owner`, `User.memberships`/`TeamMembership.user`, `Workspace.teams`/`Team.workspace`, `Team.memberships`/`TeamMembership.team`, `Workspace.projects`/`Project.workspace`, `Project.team_roles`/`ProjectTeamRole.project`, `Team.project_roles`/`ProjectTeamRole.team`. Cross-module pairs (`Workspace.projects`, `Team.project_roles`, and their back-references) use string class names; both model modules must be importable before mappers configure (already true via `app/main.py`).

- [ ] **Step 1: Write the failing tests**

In `backend/tests/identity/test_models.py`, update `_make_user` to drop the `is_personal` kwarg (both call sites) and add:

```python
def test_revoked_token_roundtrip(db_session):
    from app.identity.models import RevokedToken
    db_session.add(RevokedToken(jti="abc123", expires_at=datetime.now(timezone.utc)))
    db_session.flush()
    assert db_session.query(RevokedToken).filter_by(jti="abc123").one().jti == "abc123"


def test_relationships_traverse(db_session):
    user, ws, team = _make_user(db_session, email="rel@example.com")
    project = Project(workspace_id=ws.id, name="rel-p")
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectTeamRole(project_id=project.id, team_id=team.id, role="admin"))
    db_session.flush()
    assert user.owned_workspaces[0].id == ws.id
    assert ws.teams[0].id == team.id
    assert team.workspace.id == ws.id
    assert user.memberships[0].team_id == team.id
    assert project.workspace.id == ws.id
    assert project.team_roles[0].team_id == team.id
    assert team.project_roles[0].project_id == project.id
```

In `backend/tests/test_alembic.py`, add `"revoked_tokens"` to the expected table set in `test_identity_tables_exist`, and in `test_migration_is_head` change the assertion to `"0002" in out.stdout and "(head)" in out.stdout`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/identity/test_models.py tests/test_alembic.py -v` (cwd `backend/`)
Expected: FAIL - `RevokedToken` not importable / `is_personal` unexpected kwarg / migration head is still `0001`.

- [ ] **Step 3: Implement model + migration changes**

`backend/app/identity/models.py`: remove `is_personal` from `Workspace` and `Team`; add `RevokedToken`; add the relationships listed in Produces. `backend/app/projects/models.py`: add `Project.is_public: Mapped[bool] = mapped_column(default=False, server_default=sa.false())` and the `Project`/`ProjectTeamRole` relationships.

`backend/alembic/versions/0002_review_fixes.py` (revision `0002`, `down_revision='0001'`): `op.create_table('revoked_tokens', ...)` (`jti` String pk, `expires_at` DateTime not null, `revoked_at` DateTime server_default now() not null); `op.add_column('projects', sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.false()))`; `op.drop_column('workspaces', 'is_personal')`; `op.drop_column('teams', 'is_personal')`. `downgrade()` reverses exactly: re-add `is_personal` columns (`nullable=False, server_default=sa.false()` to satisfy NOT NULL on existing rows), drop `is_public`, drop `revoked_tokens`.

`backend/app/identity/service.py` (minimal, per Ruling 4): drop `is_personal=True` from the `Workspace`/`Team` constructors in `register_user`; `get_personal_context` filters by `Workspace.owner_user_id == user_id` and `Team.workspace_id == workspace.id` (no `is_personal` filter). Drop the `assert result.workspace.is_personal and result.team.is_personal` line in `tests/identity/test_service.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/identity/test_models.py tests/test_alembic.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/identity/models.py backend/app/projects/models.py backend/app/identity/service.py backend/alembic/versions/0002_review_fixes.py backend/tests/identity/test_models.py backend/tests/identity/test_service.py backend/tests/test_alembic.py docs/superpowers/plans/2026-10-07-review-feedback-identity-projects.md
git commit -m "feat(identity,projects): RevokedToken model, Project.is_public, drop is_personal, ORM relationships, migration 0002"
```

---

### Task 2: Token revocation - jti claim, blocklist, logout endpoint

**Files:**
- Modify: `backend/app/core/security.py`
- Modify: `backend/app/identity/service.py`
- Modify: `backend/app/identity/dependencies.py`
- Modify: `backend/app/identity/router.py`
- Test: `backend/tests/core/test_security.py`, `backend/tests/identity/test_auth_api.py`

**Interfaces:**
- Consumes: `RevokedToken` (Task 1).
- Produces:
  - `app.core.security.TokenClaims` (frozen dataclass): `user_id: UUID`, `jti: str`, `exp: datetime`.
  - `create_access_token(user_id: UUID, settings: Settings) -> str` (signature unchanged; now embeds `jti`).
  - `decode_access_token(token: str, settings: Settings) -> TokenClaims` (return type changes from `UUID`).
  - `app.identity.service.revoke_token(db: Session, jti: str, expires_at: datetime) -> None` (idempotent; commits).
  - `app.identity.service.is_token_revoked(db: Session, jti: str) -> bool`.
  - `POST /auth/logout` -> `204`, revokes the presented token's `jti`.
  - `get_current_user` now rejects revoked tokens with `401 {"detail": "invalid or expired token"}`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/core/test_security.py`, replace `test_token_roundtrip` and add:

```python
def test_token_roundtrip():
    uid = uuid.uuid4()
    token = create_access_token(uid, _settings())
    claims = decode_access_token(token, _settings())
    assert claims.user_id == uid and isinstance(claims.jti, str) and claims.jti


def test_jti_unique_across_tokens():
    uid = uuid.uuid4()
    a = decode_access_token(create_access_token(uid, _settings()), _settings())
    b = decode_access_token(create_access_token(uid, _settings()), _settings())
    assert a.jti != b.jti
```

In `backend/tests/identity/test_auth_api.py` add:

```python
def test_logout_revokes_token(client):
    r = client.post("/auth/register", json={"email": "lo@example.com", "password": "password123"})
    token = r.json()["access_token"]
    assert client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 204
    after = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert after.status_code == 401


def test_logout_leaves_other_sessions_valid(client):
    body = {"email": "two@example.com", "password": "password123"}
    t1 = client.post("/auth/register", json=body).json()["access_token"]
    t2 = client.post("/auth/login", json=body).json()["access_token"]
    assert client.post("/auth/logout", headers={"Authorization": f"Bearer {t1}"}).status_code == 204
    assert client.get("/users/me", headers={"Authorization": f"Bearer {t2}"}).status_code == 200


def test_logout_requires_auth(client):
    assert client.post("/auth/logout").status_code in (401, 403)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_security.py tests/identity/test_auth_api.py -v`
Expected: FAIL - `TokenClaims` missing, no `/auth/logout` route, `decode_access_token` returns `UUID` not `TokenClaims`.

- [ ] **Step 3: Implement**

`backend/app/core/security.py`: add `TokenClaims` frozen dataclass; `create_access_token` adds `"jti": str(uuid.uuid4())` to claims; `decode_access_token` returns `TokenClaims(user_id=..., jti=..., exp=...)`, raising `jwt.InvalidTokenError` if `jti`/`exp` missing (same wrapping style as the existing `sub` handling).

`backend/app/identity/service.py`: add `revoke_token(db, jti, expires_at)` (skip insert if `is_token_revoked`, else add `RevokedToken` + `db.commit()`) and `is_token_revoked(db, jti) -> bool`.

`backend/app/identity/dependencies.py`: `get_current_user` calls `decode_access_token`, then `is_token_revoked(db, claims.jti)` -> `401` if revoked, then `db.get(User, claims.user_id)`.

`backend/app/identity/router.py`: add `POST /auth/logout` -> decode the bearer token's claims (same `jwt.InvalidTokenError` -> `401` handling), call `revoke_token(db, claims.jti, claims.exp)`, return `Response(status_code=204)`. Logout is idempotent: an already-revoked-but-valid token re-revokes harmlessly and still returns `204`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_security.py tests/identity/test_auth_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/security.py backend/app/identity/service.py backend/app/identity/dependencies.py backend/app/identity/router.py backend/tests/core/test_security.py backend/tests/identity/test_auth_api.py
git commit -m "feat(identity): JWT jti claim, token blocklist, POST /auth/logout with per-session revocation"
```

---

### Task 3: Registration creates a default project atomically

**Files:**
- Modify: `backend/app/projects/service.py`
- Modify: `backend/app/identity/service.py`
- Modify: `backend/app/identity/router.py`
- Modify: `backend/tests/test_smoke_e2e.py` (assertion counts shift once "Default" project exists)
- Test: `backend/tests/identity/test_service.py`, `backend/tests/identity/test_users_me.py`

**Interfaces:**
- Consumes: `Project`, `ProjectTeamRole` (Task 1); `RegistrationResult` (existing).
- Produces:
  - `app.projects.service.create_project_for_team(db: Session, team: Team, name: str) -> Project` - creates Project in `team.workspace_id` + `ProjectTeamRole(team, "admin")`, `db.flush()`es but does NOT commit (caller owns the transaction).
  - `RegistrationResult` gains `project: Project`.
  - Auto-created entities are named `Default` (workspace, team, project), `Project.is_public` defaults `False`.
  - `GET /users/me` returns `{user_id, email}` only (drops `workspace_id`/`team_id`; discovery moves to Task 4's endpoints).
  - `app.identity.service.get_personal_context` is NOT touched here - `app/projects/service.create_project` still calls it until Task 5 refactors that function. It gets deleted in Task 5.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/identity/test_service.py`, replace `test_register_creates_full_personal_graph` with:

```python
def test_register_creates_default_graph(db_session):
    result = service.register_user(db_session, "new@example.com", "password123")
    assert result.workspace.owner_user_id == result.user.id
    assert result.team.workspace_id == result.workspace.id
    assert result.workspace.name == "Default" and result.team.name == "Default"
    assert result.project.name == "Default" and result.project.is_public is False
    assert result.project.workspace_id == result.workspace.id
```

In `backend/tests/identity/test_users_me.py`, change the assertion in `test_users_me_returns_ids` to `assert body["email"] == "me@example.com"` and `uuid.UUID(body["user_id"])` only (drop `workspace_id`/`team_id` checks).

Add a rollback test (Review Focus #4) to `backend/tests/identity/test_service.py` (note: `create_project_for_team` is reached via a function-level import inside `register_user`, so it is monkeypatched on `app.projects.service`, not `app.identity.service`):

```python
def test_register_rolls_back_if_project_creation_fails(db_session, monkeypatch):
    from app.projects import service as projects_service

    def boom(*args, **kwargs):
        raise RuntimeError("project creation failed")

    monkeypatch.setattr(projects_service, "create_project_for_team", boom)
    with pytest.raises(RuntimeError):
        service.register_user(db_session, "fail@example.com", "password123")
    assert db_session.query(User).filter_by(email="fail@example.com").one_or_none() is None
```

(import `User` from `app.identity.models` at the top of the file).

Also update `backend/tests/test_smoke_e2e.py`: line 19 `assert len(...) == 1` becomes `== 2` (`"Default"` + `"e2e-kb"`), and line 21 `== []` becomes `== ["Default"]` (or equivalent name-based assertions).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/identity/test_service.py tests/identity/test_users_me.py tests/test_smoke_e2e.py -v`
Expected: FAIL - `RegistrationResult` has no `project`, `/users/me` still returns `workspace_id`/`team_id`, `create_project_for_team` not patchable on `projects_service`.

- [ ] **Step 3: Implement**

`backend/app/projects/service.py`: add `create_project_for_team(db, team, name) -> Project` (build `Project(workspace_id=team.workspace_id, name=name)`, `db.add` + `db.flush`, then `ProjectTeamRole(project_id=project.id, team_id=team.id, role="admin")` + `db.flush`, return project; no `db.commit`).

`backend/app/identity/service.py`: `register_user` adds `db.add(TeamMembership(...)); db.flush()` then `project = create_project_for_team(db, team, "Default")` before the single `db.commit()`; rename workspace/team to `"Default"`; add `project` field to `RegistrationResult`. Import `create_project_for_team` with a function-level import inside `register_user` (`from app.projects.service import create_project_for_team`) to avoid a module-load circular import with `app/projects/service.py`, which still imports `get_personal_context` from this module until Task 5.

`backend/app/identity/router.py`: `/users/me` returns only `{"user_id": str(user.id), "email": user.email}` (drop `get_personal_context` call here).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/identity/test_service.py tests/identity/test_users_me.py tests/identity/test_auth_api.py tests/test_smoke_e2e.py -v`
Expected: PASS (auth tests unaffected; smoke e2e now sees "Default" + "e2e-kb").

- [ ] **Step 5: Commit**

```bash
git add backend/app/projects/service.py backend/app/identity/service.py backend/app/identity/router.py backend/tests/identity/test_service.py backend/tests/identity/test_users_me.py backend/tests/test_smoke_e2e.py
git commit -m "feat(identity,projects): registration atomically creates Default workspace/team/project; slim /users/me"
```

---

### Task 4: Workspace/team discovery endpoints

**Files:**
- Modify: `backend/app/identity/service.py`
- Modify: `backend/app/identity/schemas.py`
- Modify: `backend/app/identity/router.py`
- Test: `backend/tests/identity/test_workspaces_api.py` (new)

**Interfaces:**
- Consumes: `User`, `Workspace`, `Team`, `TeamMembership` (Task 1); `get_current_user`.
- Produces:
  - `app.identity.service.list_user_workspaces(db: Session, user: User) -> list[Workspace]` - distinct workspaces of teams the user is a member of.
  - `app.identity.service.list_workspace_teams(db: Session, user: User, workspace_id: UUID) -> list[Team] | None` - teams in `workspace_id` the user is a member of; `None` if the workspace is unknown or the user has no membership there (router returns `404 "workspace not found"`, no existence leak).
  - `app.identity.schemas.WorkspaceOut`: `id: UUID`, `name: str`.
  - `app.identity.schemas.TeamOut`: `id: UUID`, `name: str`, `workspace_id: UUID`.
  - `GET /workspaces` -> `list[WorkspaceOut]`.
  - `GET /workspaces/{workspace_id}/teams` -> `list[TeamOut]`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/identity/test_workspaces_api.py`:

```python
def _auth(client, email):
    r = client.post("/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_list_workspaces_and_teams(client):
    headers = _auth(client, "ws@example.com")
    ws = client.get("/workspaces", headers=headers).json()
    assert len(ws) == 1 and ws[0]["name"] == "Default"
    teams = client.get(f"/workspaces/{ws[0]['id']}/teams", headers=headers).json()
    assert len(teams) == 1 and teams[0]["name"] == "Default" and teams[0]["workspace_id"] == ws[0]["id"]


def test_workspace_teams_unknown_workspace_404(client):
    headers = _auth(client, "ws2@example.com")
    assert client.get("/workspaces/00000000-0000-0000-0000-000000000000/teams",
                      headers=headers).status_code == 404


def test_workspaces_require_auth(client):
    assert client.get("/workspaces").status_code in (401, 403)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/identity/test_workspaces_api.py -v`
Expected: FAIL - 404 on `GET /workspaces` (route not defined).

- [ ] **Step 3: Implement**

`backend/app/identity/service.py`: implement `list_user_workspaces` (distinct `Workspace` joined through `Team`->`TeamMembership` filtered by `user.id`) and `list_workspace_teams` (`Team` in `workspace_id` joined to `TeamMembership` filtered by `user.id`; return `None` when the result is empty). `backend/app/identity/schemas.py`: add `WorkspaceOut`, `TeamOut`. `backend/app/identity/router.py`: add `GET /workspaces` and `GET /workspaces/{workspace_id}/teams` (return `404 "workspace not found"` when the service returns `None`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/identity/test_workspaces_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/identity/service.py backend/app/identity/schemas.py backend/app/identity/router.py backend/tests/identity/test_workspaces_api.py
git commit -m "feat(identity): GET /workspaces and GET /workspaces/{id}/teams for workspace/team discovery"
```

---

### Task 5: Project creation scoped to an explicit team_id

**Files:**
- Modify: `backend/app/projects/service.py`
- Modify: `backend/app/projects/schemas.py`
- Modify: `backend/app/projects/router.py`
- Modify: `backend/app/identity/service.py` (drop now-unused `get_personal_context`)
- Modify: `backend/tests/test_smoke_e2e.py` (add `team_id` to the create call)
- Test: `backend/tests/projects/test_service.py`, `backend/tests/projects/test_projects_api.py`

**Interfaces:**
- Consumes: `create_project_for_team` (Task 3), `list_user_workspaces`/`list_workspace_teams` (Task 4), `Team`, `TeamMembership` (Task 1).
- Produces:
  - `app.projects.service.create_project(db: Session, user: User, team_id: UUID, name: str) -> Project | None` - `None` if the user is not a member of `team_id` (router returns `404 "team not found"`); otherwise creates via `create_project_for_team` and `db.commit()`s.
  - `app.projects.service.get_project_for_user(db, user, project_id)` - unchanged (team-visible only).
  - `ProjectCreate` gains `team_id: UUID`.
  - `POST /projects` body: `{"name": str, "team_id": UUID}`.
  - `app.identity.service.get_personal_context` deleted (no callers remain).

- [ ] **Step 1: Write the failing tests**

In `backend/tests/projects/test_projects_api.py`, update `test_create_and_list_projects` to first fetch a team via Task 4's endpoints (add helper) then post `{"name": "kb", "team_id": team_id}`; add:

```python
def test_create_project_rejects_foreign_team(client):
    alice = _auth(client, "fa@example.com")
    bob = _auth(client, "fb@example.com")
    bob_team_id = _default_team_id(client, bob)
    r = client.post("/projects", json={"name": "x", "team_id": bob_team_id}, headers=alice)
    assert r.status_code == 404
```

with module-level helper:

```python
def _default_team_id(client, headers):
    ws = client.get("/workspaces", headers=headers).json()[0]
    return client.get(f"/workspaces/{ws['id']}/teams", headers=headers).json()[0]["id"]
```

In `backend/tests/projects/test_service.py`, update `test_create_project_grants_personal_team_admin` to call `project_service.create_project(db_session, user, team_id, "kb1")` where `team_id` comes from `identity_service.list_workspace_teams(...)`/DB lookup; drop the `identity_service.get_personal_context` usage in `test_get_project_for_user_with_role_requires_admin` (query `TeamMembership`/`Team` directly for the viewer's team instead).

Also update `test_create_and_list_projects`'s list assertion in `backend/tests/projects/test_projects_api.py`: since registration (Task 3) now auto-creates a `"Default"` project in the same team, `== ["kb"]` becomes a membership check (`"kb" in names` and `"Default" in names`), or filter to `p["name"] == "kb"` explicitly.

Also update `backend/tests/test_smoke_e2e.py` line 17 to fetch a `team_id` first (same `_default_team_id` helper pattern as `test_projects_api.py`, or inline via `/workspaces` + `/workspaces/{id}/teams`) and post `{"name": "e2e-kb", "team_id": team_id}`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/projects/ -v`
Expected: FAIL - `create_project` takes 3 positional args (no `team_id`), `get_personal_context` import error.

- [ ] **Step 3: Implement**

`backend/app/projects/service.py`: add `_get_team_for_member(db, user, team_id) -> Team | None` (Team joined to `TeamMembership` filtered by `user.id` and `team_id`, `one_or_none`); rewrite `create_project(db, user, team_id, name) -> Project | None` to resolve the team (return `None` if absent), delegate to `create_project_for_team`, `db.commit()`. `backend/app/projects/schemas.py`: `ProjectCreate.team_id: UUID`. `backend/app/projects/router.py`: pass `body.team_id`, return `404 "team not found"` when `create_project` returns `None`. `backend/app/identity/service.py`: delete `get_personal_context` (and its `Workspace`/`Team` filter imports if unused).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/projects/ tests/identity/ tests/test_smoke_e2e.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/projects/service.py backend/app/projects/schemas.py backend/app/projects/router.py backend/app/identity/service.py backend/tests/projects/test_service.py backend/tests/projects/test_projects_api.py backend/tests/test_smoke_e2e.py
git commit -m "feat(projects): project creation requires an explicit member team_id; drop get_personal_context"
```

---

### Task 6: Public project visibility + PATCH

**Files:**
- Modify: `backend/app/projects/service.py`
- Modify: `backend/app/projects/schemas.py`
- Modify: `backend/app/projects/router.py`
- Test: `backend/tests/projects/test_projects_api.py`, `backend/tests/projects/test_service.py`

**Interfaces:**
- Consumes: `Project.is_public` (Task 1), `get_project_for_user_with_role` (existing).
- Produces:
  - `app.projects.service.get_project_visible_to_user(db: Session, user: User, project_id: UUID) -> Project | None` - team-visible OR `is_public=True`.
  - `app.projects.service.list_public_projects(db: Session) -> list[Project]` - all `is_public=True`.
  - `app.projects.service.update_project(db: Session, project: Project, name: str | None = None, is_public: bool | None = None) -> Project` (commits).
  - `ProjectUpdate`: `name: str | None` (min 1, max 200), `is_public: bool | None`.
  - `ProjectOut` gains `is_public: bool`.
  - `GET /projects/public` -> `list[ProjectOut]` (declared BEFORE `GET /projects/{project_id}` so `public` is not captured as an id).
  - `PATCH /projects/{project_id}` -> `ProjectOut`, `404 "project not found"` unless team `admin`.
  - `GET /projects/{project_id}` now returns public projects to non-members.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/projects/test_projects_api.py`:

```python
def test_public_project_visible_to_non_member(client):
    alice = _auth(client, "pa@example.com")
    bob = _auth(client, "pb@example.com")
    pid = client.post("/projects", json={"name": "pub", "team_id": _default_team_id(client, alice)},
                      headers=alice).json()["id"]
    client.patch(f"/projects/{pid}", json={"is_public": True}, headers=alice)
    assert client.get(f"/projects/{pid}", headers=bob).status_code == 200
    assert any(p["id"] == pid for p in client.get("/projects/public", headers=bob).json())
    assert [p["name"] for p in client.get("/projects", headers=bob).json()] == ["Default"]


def test_public_project_not_editable_by_non_member(client):
    alice = _auth(client, "qa@example.com")
    bob = _auth(client, "qb@example.com")
    pid = client.post("/projects", json={"name": "pub2", "team_id": _default_team_id(client, alice)},
                      headers=alice).json()["id"]
    client.patch(f"/projects/{pid}", json={"is_public": True}, headers=alice)
    assert client.patch(f"/projects/{pid}", json={"name": "hax"}, headers=bob).status_code == 404
    assert client.delete(f"/projects/{pid}", headers=bob).status_code == 404


def test_patch_updates_name_and_visibility(client):
    h = _auth(client, "pu@example.com")
    pid = client.post("/projects", json={"name": "old", "team_id": _default_team_id(client, h)},
                      headers=h).json()["id"]
    r = client.patch(f"/projects/{pid}", json={"name": "new", "is_public": True}, headers=h)
    assert r.status_code == 200 and r.json()["name"] == "new" and r.json()["is_public"] is True
```

Note: `test_create_and_list_projects`'s list assertion was already updated in Task 5 to account for the auto-created `"Default"` project - no further change needed here.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/projects/test_projects_api.py -v`
Expected: FAIL - `GET /projects/public` 404, `PATCH` 405/404, `is_public` not in `ProjectOut`.

- [ ] **Step 3: Implement**

`backend/app/projects/service.py`: add `get_project_visible_to_user` (try `get_project_for_user`, else fall back to `Project.id == project_id, Project.is_public.is_(True)`), `list_public_projects`, `update_project`. `backend/app/projects/schemas.py`: add `ProjectUpdate`, add `is_public` to `ProjectOut`. `backend/app/projects/router.py`: add `GET /projects/public` (before `GET /projects/{project_id}`) and `PATCH /projects/{project_id}` (authorize via `get_project_for_user_with_role(roles=("admin",))`, then `update_project`); switch `GET /projects/{project_id}` to `get_project_visible_to_user`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/projects/ tests/identity/ tests/test_smoke_e2e.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/projects/service.py backend/app/projects/schemas.py backend/app/projects/router.py backend/tests/projects/test_projects_api.py backend/tests/projects/test_service.py
git commit -m "feat(projects): Project.is_public visibility, GET /projects/public, PATCH /projects/{id} (admin only)"
```

---

### Task 7: Sync the design spec with the revised model

**Files:**
- Modify: `docs/superpowers/specs/2026-10-06-rag-mvp-slices-design.md`

**Interfaces:**
- Consumes: all code decisions from Tasks 1-6.
- Produces: spec §4.1 data model, §4.2 endpoints, §4.3 auth decisions match the shipped code.

- [ ] **Step 1: Update §4.1 data model block**

Remove `is_personal bool` from `workspaces` and `teams`; add `is_public bool` to `projects`; add a `revoked_tokens` table row (`jti` (text pk), `expires_at`, `revoked_at`). Update the prose in §4.1 (the `project_team_roles` paragraph) to say registration creates the user + Default workspace + Default team + membership + a Default project in one transaction, and that project creation takes an explicit `team_id` whose team gets `admin`.

- [ ] **Step 2: Update §4.2 endpoints block**

Add `POST /auth/logout`, `GET /workspaces`, `GET /workspaces/{id}/teams`, `GET /projects/public`, `PATCH /projects/{id}`. Change `POST /projects` to `{name, team_id}`. Change `GET /users/me` description to "current user (id, email) only".

- [ ] **Step 3: Update §4.3 auth decisions**

Note the `jti` claim and the `revoked_tokens` blocklist for per-session logout.

- [ ] **Step 4: Verify consistency**

Read the updated spec sections back against `backend/app/` and confirm no `is_personal` reference remains in the spec's data model or endpoint sections.

Run: `git diff --stat docs/superpowers/specs/2026-10-06-rag-mvp-slices-design.md`
Expected: only the three sections above changed.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-10-06-rag-mvp-slices-design.md
git commit -m "docs: sync S1 design spec with revised identity/projects model"
```
