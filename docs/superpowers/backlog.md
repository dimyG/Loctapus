# Backlog

Follow-ups and consciously deferred findings. The S0/S1 review's deferred minors were
all resolved on 2026-10-08 (in the `fix-deferred-minors` branch, merged to master);
the items below remain open.

## Todo later

- Background job (probably a Celery beat task) that clears expired JWTs from the
  revoked-token table.
- Replace MinIO with a maintained S3-compatible server (SeaweedFS or Garage) before S2
  storage work builds on it; MinIO's community edition reached end-of-life in February
  2026, so no official registry image will return. Also tracked as a TODO comment in
  `deploy/docker-compose.yml`.