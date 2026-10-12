# Backlog

Follow-ups and consciously deferred findings. The S0/S1 review's deferred minors were
all resolved on 2026-10-08 (in the `fix-deferred-minors` branch, merged to master).
The deferred minors from the 2026-10-07 review-feedback session were all resolved on
2026-10-09 in the `fix-deferred-minors-2` branch.


## Todo later

- 2026-10-12 - vitest suite under extreme parallel load (S2 footer/about work, commits up to
  `1f3c76d`): running three full `npm run test` suites concurrently on this machine starves
  jsdom workers; userEvent typing tests (RegisterPage "does not post on mismatch", LoginPage
  401 copy) time out at the 10s budget. Reproducible at commit `be6ebcd` too, so pre-existing,
  and never seen on single runs. The root-redirect test additionally starved React transitions
  until it got a real 5s wait budget (`fd71039`); a 4-arg `findByRole` call had silently dropped
  the timeout option. Candidate fix: vitest `pool: "vmThreads"` per its environment hint.
- The 2026-10-09 pending human visual pass should now also cover the shared site footer on all
  layouts and the /about page (commits `4d6b83f`, `af03aa2`, `52d3b58`).
- Frontend JWT lives in localStorage (chosen at the S2 design round, 2026-10-09): a script
  injected via XSS can read it. S2 renders no user-supplied HTML so the surface is our own
  code. Possible later upgrade to httpOnly cookies (needs Set-Cookie + CSRF handling in the
  S1 API) is contained to `web/src/lib/tokenStorage.ts` plus the base API client.
- Background job (probably a Celery beat task) that clears expired JWTs from the
  revoked-token table.
- Replace MinIO with a maintained S3-compatible server (SeaweedFS or Garage) before S3
  (ingestion) storage work builds on it; MinIO's community edition reached end-of-life in
  February 2026, so no official registry image will return. Also tracked as a TODO
  comment in `deploy/docker-compose.yml`.
- Review how to store dates: aware in utc, or as timestamps in msec
- S2's three-width visual check ran as an automated audit (no horizontal overflow at
  390/768/1280, body-text contrast at or above 4.5, no text under 14px) plus saved
  screenshots in the S2 worktree (`.superpowers/sdd/2026-10-09-s2-web-ui-foundations/visual/`,
  git-ignored) - a human eyeball pass of those pages is still pending; note any
  polish here. (S2 e2e slice, commit `14b3f6d`.)


## 2026-10-09 - deferred minors in `fix-deferred-minors-2`, kept open by its final review

- `revoke_token` calls `on_conflict_do_nothing()` without a conflict target, so the
  SQL suppresses violations of every unique constraint on `revoked_tokens` while the
  comment names only the jti primary key; pass `index_elements=[RevokedToken.jti]`
  (from commit `c9942f7`).