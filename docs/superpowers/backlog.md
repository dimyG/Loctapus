# Backlog

Follow-ups and consciously deferred findings. The S0/S1 review's deferred minors were
all resolved on 2026-10-08 (in the `fix-deferred-minors` branch, merged to master).
The deferred minors from the 2026-10-07 review-feedback session were all resolved on
2026-10-09 in the `fix-deferred-minors-2` branch.


## Todo later

- Background job (probably a Celery beat task) that clears expired JWTs from the
  revoked-token table.
- Replace MinIO with a maintained S3-compatible server (SeaweedFS or Garage) before S3
  (ingestion) storage work builds on it; MinIO's community edition reached end-of-life in
  February 2026, so no official registry image will return. Also tracked as a TODO
  comment in `deploy/docker-compose.yml`.
- Review how to store dates: aware in utc, or as timestamps in msec


## 2026-10-09 - deferred minors in `fix-deferred-minors-2`, kept open by its final review

- `revoke_token` calls `on_conflict_do_nothing()` without a conflict target, so the
  SQL suppresses violations of every unique constraint on `revoked_tokens` while the
  comment names only the jti primary key; pass `index_elements=[RevokedToken.jti]`
  (from commit `c9942f7`).