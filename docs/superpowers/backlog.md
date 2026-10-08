# Backlog

Follow-ups and consciously deferred findings. The S0/S1 review's deferred minors were
all resolved on 2026-10-08 (in the `fix-deferred-minors` branch, merged to master).
The deferred minors from the 2026-10-07 review-feedback session are tracked below;
its timestamps finding was resolved by migration 0003, the rest remain open.


## Deferred minors
- Concurrently logging out the same token twice can raise IntegrityError and surface
  500 (`revoke_token` is check-then-insert); use INSERT ... ON CONFLICT DO NOTHING.
- `register_user` maps every IntegrityError to `EmailAlreadyRegisteredError`, so a
  constraint failure while provisioning the default workspace/team/project would be
  reported as a duplicate email; narrow the except to the user-flush block.
- The logout route duplicates `get_current_user`'s token decode and 401 handling;
  extract a shared `get_token_claims` FastAPI dependency.
- `PATCH /projects/{id}` silently ignores explicit nulls (`{"name": null}`); decide
  whether to reject them via `model_fields_set`.
- Revocation is only asserted through `/users/me` in the tests; add a request to
  `/projects` with a revoked token to pin the every-endpoint guarantee.
- Migration 0002's downgrade re-adds `is_personal` as all-false; a backfill UPDATE
  would restore pre-0002 semantics under a full code-and-schema rollback.


## Todo later

- Background job (probably a Celery beat task) that clears expired JWTs from the
  revoked-token table.
- Replace MinIO with a maintained S3-compatible server (SeaweedFS or Garage) before S2
  storage work builds on it; MinIO's community edition reached end-of-life in February
  2026, so no official registry image will return. Also tracked as a TODO comment in
  `deploy/docker-compose.yml`.
- Review how to store dates: aware in utc, or as timestamps in msec