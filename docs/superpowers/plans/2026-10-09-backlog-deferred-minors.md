# Backlog Deferred Minors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the six still-open deferred minors from the 2026-10-07 review-feedback session listed in `docs/backlog.md`.

**Architecture:** Four small fixes in the identity layer (race-free revocation insert, honest registration error mapping, shared token-decode dependency, revocation pinned on another endpoint), one projects-schema decision (reject explicit PATCH nulls), and one migration downgrade backfill, each landing as its own commit in a dedicated worktree.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 (PostgreSQL dialect), Alembic, pytest.

**Spec:** `docs/backlog.md`, section "Deferred minors" (all six bullets). Relevance of each was verified against master `efe0f29` on 2026-10-09; all six are still present in the code.

## Global Constraints

- All function parameters keyword-only (`PLR0917`), also in tests' helper stubs.
- Ruff line length 110; docstrings on every module/class/function including private ones, followed by a blank line; comments start with a capital letter and end with a dot; never use the em dash.
- Verification commands run from `backend/`: `ruff check .`, `mypy app tests`, `pytest`. Tests need Postgres at `RAG_TEST_DATABASE_URL` or the default `postgresql+psycopg://rag:rag@localhost:5432/rag_test`.
- One concern per commit; work on branch `fix-deferred-minors-2` in a worktree created via superpowers:using-git-worktrees.
- Two decisions are pending the human partner's confirmation at plan review: D1 (Task 4, reject explicit PATCH nulls with 422) and D2 (Task 6, backfill `is_personal = TRUE` for all rows). The tasks below implement the recommended options.

## Review Focus

- Two concurrent logouts of the same token both answer 204, never a 500 from an IntegrityError. Pinned in Task 1.
- A registration whose provisioning (workspace/team/project) hits a constraint failure propagates as itself with a full rollback, not as a fake "email already registered" 409. Pinned in Task 2.
- Logout with a malformed or expired bearer token answers the standard 401, identical to `/users/me`. Pinned in Task 3.
- `PATCH /projects/{id}` with an explicit null field answers 422 instead of silently ignoring it. Pinned in Task 4.
- Running the 0002 downgrade on a database that holds rows restores pre-0002 `is_personal` semantics instead of leaving all-false flags. Pinned in Task 6.
- A revoked token is rejected on every protected endpoint, not just `/users/me`; the spec explicitly asks for `/projects`. Pinned in Task 5.

---

### Task 1: Race-free token revocation

**Files:**
- Modify: `backend/app/identity/service.py:65-70` (`revoke_token`)
- Test: `backend/tests/identity/test_service.py`

**Interfaces:**
- Consumes: `RevokedToken`, `db: Session`, `jti: str`, `expires_at: datetime`.
- Produces: `revoke_token(*, db: Session, jti: str, expires_at: datetime) -> None`, unchanged signature; no longer consults `is_token_revoked` (which stays for `get_current_user`).

- [ ] **Step 1: Write the failing test**

```python
def test_revoke_token_tolerates_concurrent_duplicate(
    *, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that a second, concurrent revoke of the same jti cannot raise IntegrityError."""

    expires_at = datetime.now(UTC)
    service.revoke_token(db=db_session, jti="race-jti", expires_at=expires_at)

    # Simulate the losing interleaving of two concurrent logouts: both pre-checks miss
    # the row, so both inserts run. With check-then-insert the second one raises.
    def blind(*, db: Session, jti: str) -> bool:
        """Report every token as unrevoked, as a concurrent pre-check would."""

        return False

    monkeypatch.setattr(service, "is_token_revoked", blind)
    service.revoke_token(db=db_session, jti="race-jti", expires_at=expires_at)
    assert db_session.get(RevokedToken, "race-jti") is not None
```

Add imports: `from datetime import UTC, datetime` and `from app.identity.models import RevokedToken` (keep `User`).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/identity/test_service.py::test_revoke_token_tolerates_concurrent_duplicate -v`
Expected: FAIL with IntegrityError (unique violation on `revoked_tokens_pkey`).

- [ ] **Step 3: Implement the ON CONFLICT insert in `revoke_token`**

Replace the check-then-insert body with a PostgreSQL dialect insert: `insert(RevokedToken).values(...).on_conflict_do_nothing()`, then `db.execute(stmt)` and `db.commit()`. Import `insert` from `sqlalchemy.dialects.postgresql` (tests run on Postgres only, per `tests/conftest.py`). Docstring: "Record a token as revoked; repeated or concurrent calls with the same jti are a no-op." Add a one-line comment explaining that the conflict target is the jti primary key.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/identity/test_service.py -v`
Expected: PASS, including the pre-existing service tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/identity/service.py backend/tests/identity/test_service.py
git commit -m "fix(identity): revoke_token inserts with ON CONFLICT DO NOTHING"
```

### Task 2: Narrow the duplicate-email mapping in register_user

**Files:**
- Modify: `backend/app/identity/service.py:30-53` (`register_user`)
- Test: `backend/tests/identity/test_service.py`

**Interfaces:**
- Produces: `register_user(*, db: Session, email: str, password: str) -> RegistrationResult`, unchanged signature and `EmailAlreadyRegisteredError` semantics for duplicate emails.

- [ ] **Step 1: Write the failing test**

```python
def test_register_provisioning_failure_not_email_conflict(
    *, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that a constraint failure while provisioning surfaces as itself, not a 409."""

    def boom(*args: object, **kwargs: object) -> None:
        """Fail provisioning to exercise the propagation path."""

        raise IntegrityError("insert into workspaces", {}, Exception("check violation"))

    monkeypatch.setattr(service, "create_project_for_team", boom)
    with pytest.raises(IntegrityError):
        service.register_user(db=db_session, email="prov@example.com", password="password123")
    assert db_session.query(User).filter_by(email="prov@example.com").one_or_none() is None
```

Import `IntegrityError` from `sqlalchemy.exc` in the test module.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/identity/test_service.py::test_register_provisioning_failure_not_email_conflict -v`
Expected: FAIL - the call raises `EmailAlreadyRegisteredError` instead of `IntegrityError`.

- [ ] **Step 3: Split the try block in `register_user`**

Keep `db.add(user)` first. One try block around only `db.flush()` for the user, with `except IntegrityError: db.rollback(); raise EmailAlreadyRegisteredError(email) from None` (the only constraint the user insert can violate is the unique email). A second try block around the workspace/team/membership/project provisioning and `db.commit()` with `except Exception: db.rollback(); raise` so failures propagate as themselves. Keep one comment noting that only the user flush can mean a duplicate email.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/identity/test_service.py -v`
Expected: PASS, including `test_register_duplicate_email_raises` and `test_register_rolls_back_if_project_creation_fails`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/identity/service.py backend/tests/identity/test_service.py
git commit -m "fix(identity): map only the user flush to EmailAlreadyRegisteredError"
```

### Task 3: Shared get_token_claims dependency

**Files:**
- Modify: `backend/app/identity/dependencies.py`
- Modify: `backend/app/identity/router.py:104-118` (`logout`) and its imports
- Test: `backend/tests/identity/test_auth_api.py`

**Interfaces:**
- Consumes: `decode_access_token`, `TokenClaims` from `app.core.security`, `Settings`, `get_settings`, `HTTPBearer`.
- Produces: `get_token_claims(*, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()), settings: Settings = Depends(get_settings)) -> TokenClaims` in `app.identity.dependencies`, raising `HTTPException(401, "invalid or expired token")` on `jwt.InvalidTokenError`.

- [ ] **Step 1: Add the pinning test**

```python
def test_logout_rejects_garbage_token(*, client: TestClient) -> None:
    """Check that logout answers 401 for a malformed bearer token."""

    r = client.post("/auth/logout", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401
    assert r.json() == {"detail": "invalid or expired token"}
```

Run: `pytest tests/identity/test_auth_api.py::test_logout_rejects_garbage_token -v`
Expected: PASS already; it pins the behavior the refactor must preserve.

- [ ] **Step 2: Extract `get_token_claims` in `dependencies.py`**

Move the try/decode/401 block from `get_current_user` into a new `get_token_claims` dependency (docstring: "Return the verified claims of the bearer token, raising 401 when it is invalid."). `get_current_user` then takes `claims: TokenClaims = Depends(get_token_claims)` plus `db` and keeps only the revocation check and user lookup. Import `TokenClaims` alongside `decode_access_token`.

- [ ] **Step 3: Use the dependency in `logout`**

The logout route takes `claims: TokenClaims = Depends(get_token_claims)` and `db`, drops `credentials`/`settings` params, and calls `revoke_token(db=db, jti=claims.jti, expires_at=claims.exp)`. Remove the now-unused `jwt`, `HTTPAuthorizationCredentials`, `HTTPBearer`, and `decode_access_token` imports from `router.py` (`Settings`, `get_settings`, `create_access_token` stay for register/login).

- [ ] **Step 4: Run the identity and e2e suites**

Run: `pytest tests/identity tests/test_smoke_e2e.py -v`
Expected: PASS with no behavior change.

- [ ] **Step 5: Commit**

```bash
git add backend/app/identity/dependencies.py backend/app/identity/router.py backend/tests/identity/test_auth_api.py
git commit -m "refactor(identity): share token decode and 401 in get_token_claims"
```

### Task 4: Reject explicit nulls in PATCH /projects/{id} (decision D1)

**Files:**
- Modify: `backend/app/projects/schemas.py:16-20` (`ProjectUpdate`)
- Test: `backend/tests/projects/test_projects_api.py`

**Interfaces:**
- Produces: `ProjectUpdate` rejecting any field explicitly set to null with a Pydantic `ValueError` (FastAPI answers 422); omitted fields keep the "leave unchanged" semantics.

- [ ] **Step 1: Write the failing test**

```python
def test_patch_rejects_explicit_nulls(*, client: TestClient) -> None:
    """Check that an explicit null in a patch body is rejected instead of ignored."""

    h = _auth(client=client, email="null@example.com")
    pid = client.post(
        "/projects",
        json={"name": "nulled", "team_id": _default_team_id(client=client, headers=h)},
        headers=h,
    ).json()["id"]
    assert client.patch(f"/projects/{pid}", json={"name": None}, headers=h).status_code == 422
    assert client.patch(f"/projects/{pid}", json={"is_public": None}, headers=h).status_code == 422
    assert client.get(f"/projects/{pid}", headers=h).json()["name"] == "nulled"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/projects/test_projects_api.py::test_patch_rejects_explicit_nulls -v`
Expected: FAIL - both patch calls currently return 200 and silently ignore the null.

- [ ] **Step 3: Add a model validator to `ProjectUpdate`**

Follow the house pattern of `Settings._reject_default_secret_in_production` in `app/core/config.py`: a `@model_validator(mode="after")` method `_reject_explicit_nulls(self) -> Self` with a docstring, which iterates `self.model_fields_set` and raises `ValueError(f"{field} must not be null; omit the field to leave it unchanged")` when `getattr(self, field) is None`. Update the class docstring to state that explicit nulls are rejected. Import `Self` from `typing` and `model_validator` from `pydantic`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/projects -v`
Expected: PASS, including `test_patch_updates_name_and_visibility` (omitted fields stay unchanged).

- [ ] **Step 5: Commit**

```bash
git add backend/app/projects/schemas.py backend/tests/projects/test_projects_api.py
git commit -m "fix(projects): reject explicit null fields in PATCH with 422"
```

### Task 5: Pin revocation on /projects

**Files:**
- Test: `backend/tests/identity/test_auth_api.py`

**Interfaces:**
- Consumes: the existing register/logout API and `get_current_user` on `/projects`.

- [ ] **Step 1: Write the pinning test**

```python
def test_revoked_token_rejected_on_projects(*, client: TestClient) -> None:
    """Check that a revoked token is rejected on protected endpoints beyond /users/me."""

    token = client.post(
        "/auth/register", json={"email": "rev2@example.com", "password": "password123"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.get("/projects", headers=headers).status_code == 401
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/identity/test_auth_api.py::test_revoked_token_rejected_on_projects -v`
Expected: PASS already; the test pins the every-endpoint guarantee requested by the spec.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/identity/test_auth_api.py
git commit -m "test(identity): pin revoked-token 401 on /projects"
```

### Task 6: Backfill is_personal in the 0002 downgrade (decision D2)

**Files:**
- Modify: `backend/alembic/versions/0002_review_fixes.py:34-40` (`downgrade`)
- Test: `backend/tests/test_alembic.py`

**Interfaces:**
- Consumes: the scratch-database pattern of `test_migrations_downgrade_to_base` and its `_terminate_and_drop` helper.

- [ ] **Step 1: Write the failing test**

Add `test_0002_downgrade_backfills_is_personal` to `tests/test_alembic.py`, following the scratch-database setup of `test_migrations_downgrade_to_base` (admin engine with AUTOCOMMIT, scratch db `rag_test_0002_backfill`, alembic Config with `sqlalchemy.url` and `script_location` set, `command.upgrade(config, "head")`), then:

```python
    with scratch.connect() as conn:
        conn.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, 'h')"),
            [{"id": uid, "email": email} for uid, email in user_rows],
        )
        conn.execute(
            text("INSERT INTO workspaces (id, name, owner_user_id) VALUES (:id, :name, :owner)"),
            [
                {"id": w1, "name": "Default", "owner": user_rows[0][0]},
                {"id": w2, "name": "Personal", "owner": user_rows[1][0]},
            ],
        )
        conn.execute(
            text("INSERT INTO teams (id, workspace_id, name) VALUES (:id, :ws, :name)"),
            [
                {"id": t1, "ws": w1, "name": "Default"},
                {"id": t2, "ws": w2, "name": "Personal"},
            ],
        )
        conn.commit()
    command.downgrade(config, "0001")
    with scratch.connect() as conn:
        ws_flags = dict(conn.execute(text("SELECT name, is_personal FROM workspaces")).all())
        team_flags = dict(conn.execute(text("SELECT name, is_personal FROM teams")).all())
    assert ws_flags == {"Default": True, "Personal": True}
    assert team_flags == {"Default": True, "Personal": True}
```

Generate the ids with `uuid.uuid4()` and two `user_rows` entries (emails `d1@example.com`, `d2@example.com`); the "Personal" pair stands for a workspace registered before 0002 renamed existing rows. The `finally` block disposes both engines and calls `_terminate_and_drop` exactly like the existing test. Give the test a one-line docstring: "Check that the 0002 downgrade restores pre-0002 personal flags on existing rows."

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_alembic.py::test_0002_downgrade_backfills_is_personal -v`
Expected: FAIL - both flag dicts come back all-False from the server default.

- [ ] **Step 3: Add the backfill UPDATEs to the downgrade**

After the two `op.add_column` calls in `downgrade()` (the columns must exist first), add `op.execute("UPDATE teams SET is_personal = TRUE")` and `op.execute("UPDATE workspaces SET is_personal = TRUE")` with a comment explaining why: registration is the only creation path in 0002+ code, so every row is the owner's registration-bootstrapped workspace/team, which is what pre-0002 `get_personal_context` selected on.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_alembic.py -v`
Expected: PASS, including `test_migrations_downgrade_to_base` and `test_single_head_revision`.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/0002_review_fixes.py backend/tests/test_alembic.py
git commit -m "fix(db): 0002 downgrade backfills is_personal for registration rows"
```

### Task 7: Backlog bookkeeping, full verification, fresh-context review

**Files:**
- Modify: `docs/backlog.md`

**Interfaces:**
- Consumes: all six resolved tasks.

- [ ] **Step 1: Update the backlog**

Rewrite the intro paragraph to record that the remaining deferred minors were resolved on 2026-10-09 in the `fix-deferred-minors-2` branch, and remove the now-resolved bullets from "Deferred minors" (keep the "Todo later" section untouched). Follow the wording style of the existing note about the 2026-10-08 resolution.

- [ ] **Step 2: Full verification from `backend/`**

Run: `ruff check .` then `mypy app tests` then `pytest`
Expected: all three pass with no new findings.

- [ ] **Step 3: Commit the docs change**

```bash
git add docs/backlog.md
git commit -m "docs(backlog): record deferred minors resolved in fix-deferred-minors-2"
```

- [ ] **Step 4: Fresh-context review**

Dispatch a `general` subagent to review the whole `fix-deferred-minors-2` branch against this plan and the spec bullets, then address its findings with dedicated commits.
