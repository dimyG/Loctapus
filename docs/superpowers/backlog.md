# Backlog

Deferred findings and follow-ups from the S0/S1 scaffolding slice, carried over from the
2026-10-07 fresh-context review ledger. The Important review findings were fixed at the
time with tests; the items below were consciously deferred. Resolve or explicitly discard
them during later slices rather than carrying them forward silently.

## Deferred minors

- The expired-token test (`test_users_me_expired_token_401`) asserts only the generic
  "invalid or expired token" detail, so it would still pass if expired tokens were
  rejected for the wrong reason.
- `created_at` columns are timezone-naive.
- No production guard rejecting the development JWT secret.
- The MinIO image tag is unpinned (`elestio/minio:latest`).
- Foreign key columns have no indexes (Postgres does not create them automatically).
- `list_projects` fetches duplicate rows when a project is shared with several of the
  user's teams; the ORM deduplicates entities by primary key and a regression test
  covers the behavior, but the query should still gain `distinct()` to stop fetching the
  redundant rows.
- Missing credentials on HTTPBearer-protected endpoints produce 403 where 401 is the
  conventional status for unauthenticated requests.
- `test_migration_is_head` hardcodes the Windows venv-relative `alembic.exe` path, which
  breaks if the venv moves or on other platforms.
- Migration 0001's downgrade drops the tables but leaves the `citext` extension behind.
- There is no README; in particular the `alembic upgrade head` step against the dev
  database is undocumented.
- Two test names describe the history they overcame rather than current behavior; rename
  for clarity.
- Session teardown emits an SAWarning; rollback isolation was verified intact.

## Todo later

- Background job (probably a Celery beat task) that clears expired JWTs from the
  revoked-token table.
- Replace MinIO with a maintained S3-compatible server (SeaweedFS or Garage) before S2
  storage work builds on it; MinIO's community edition reached end-of-life in February
  2026, so no official registry image will return. Also tracked as a TODO comment in
  `deploy/docker-compose.yml`.
