# Backlog

Follow-ups and consciously deferred findings. The S0/S1 review's deferred minors were
all resolved on 2026-10-08 (in the `fix-deferred-minors` branch, merged to master).
The deferred minors from the 2026-10-07 review-feedback session were all resolved on
2026-10-09 in the `fix-deferred-minors-2` branch.


## 2026-10-12 - post-merge review of the sign-out race fix (`be2f039`)

- A hung `/auth/logout` revocation POST can clobber a fresh login: if the
  revocation outlasts a full sign-out then sign-in round trip, the late
  `logoutUser.fulfilled` matcher nulls the new session and bounces the user
  off /projects once (self-heals on reload; the old code had the same clobber
  with `idle`). Candidate fix: check the request id in the matcher, or
  serialize the thunks.
- `RequireAuth`'s `signedout` destination and `UserMenu`'s sign-out
  `navigate("/")` are string-coupled; a shared constant would make the
  coupling structural. Both docstrings document it today.


## Todo later

- 2026-10-12 - README.md covers only the backend: the done-summary does not mention the
  landed S2 web UI, and Setup/Run/Test have no `web/` instructions (npm install,
  `npm run dev`, vitest, Playwright). Predates S2 (README created at `7b1e1d2`);
  flagged by the review of the S2-done/S3-split spec update (`1601822`, `9c07b18`).
  Needs a dedicated docs pass adding the web setup/run/test sections.
- 2026-10-12 - vitest suite under extreme parallel load (S2 footer/about work, commits up to
  `1f3c76d`): running three full `npm run test` suites concurrently on this machine starves
  jsdom workers; userEvent typing tests (RegisterPage "does not post on mismatch", LoginPage
  401 copy) time out at the 10s budget. Reproducible at commit `be6ebcd` too, so pre-existing,
  and never seen on single runs. The root-redirect test additionally starved React transitions
  until it got a real 5s wait budget (`fd71039`); a 4-arg `findByRole` call had silently dropped
  the timeout option. Candidate fix: vitest `pool: "vmThreads"` per its environment hint.
- 2026-10-12 - Changing the embedding model or dimension (S5 swaps the stub constant
  `STUB_EMBEDDING_DIM` for Voyage) invalidates every stored vector, so it needs
  re-embedding, not just a dimension migration: clear `chunks.embedding`, re-enqueue a
  `document_ready_for_embedding` outbox event per existing document, and let sources
  travel indexing -> ready again. Re-embedding can run from persisted `chunks.text`, so
  no re-parse is needed. The S3 spec adds the matching `STUB_EMBEDDING_DIM` comment
  (dimension changes require an Alembic migration); this re-embedding flow is the
  deferred half.
- 2026-10-12 - S7 needs stuck-run recovery (S3 spec section 10 risk table): a worker
  crash mid-run leaves its `ingestion_runs` row - and the derived source status -
  non-terminal forever, and S3 deliberately has no re-drive path (the claim guard
  rejects re-delivery of a non-queued run). A stale-run sweep/re-drive belongs with
  the S7 robustness work. Flagged by the 2026-10-12 S3 spec review (branch
  `s3-spec-review-fixes`).
- The 2026-10-09 pending human visual pass should now also cover the shared site footer on all
  layouts and the /about page (commits `4d6b83f`, `af03aa2`, `52d3b58`).
- Frontend JWT lives in localStorage (chosen at the S2 design round, 2026-10-09): a script
  injected via XSS can read it. S2 renders no user-supplied HTML so the surface is our own
  code. Possible later upgrade to httpOnly cookies (needs Set-Cookie + CSRF handling in the
  S1 API) is contained to `web/src/lib/tokenStorage.ts` plus the base API client.
- Background job (probably a Celery beat task) that clears expired JWTs from the
  revoked-token table.
- Review how to store dates: aware in utc, or as timestamps in msec
- S2's three-width visual check ran as an automated audit (no horizontal overflow at
  390/768/1280, body-text contrast at or above 4.5, no text under 14px) plus saved
  screenshots in the S2 worktree (`.superpowers/sdd/2026-10-09-s2-web-ui-foundations/visual/`,
  git-ignored) - a human eyeball pass of those pages is still pending; note any
  polish here. (S2 e2e slice, commit `14b3f6d`.)


## 2026-10-13 - Task 5, structure-aware chunker (`0ae199e`)

- `chunk_elements` does not skip whitespace-only paragraph elements: one arriving
  between paragraphs would leave a stray `\n\n` separator in the joined chunk text,
  and one arriving alone would be emitted as an empty chunk. Unreachable today - the
  stub parser strips and skips empty text before elements reach the chunker - but
  worth hardening when real Unstructured replaces the stub at S5.


## 2026-10-13 - Task 8, ingestion and embed pipeline services (`3587104`)

- `ingest_source_item`'s fetch-failure branch (storage error -> conditional `failed`
  against `expected='fetching'`) has no direct test: the task brief fixes the test
  list, its cases stop at parse-time and conflict-time failures, and a missing-object
  seed was not among them. The branch shares `_mark_run_failed` with three covered
  paths; add a missing-key delivery test when a later task touches this service again.


## 2026-10-13 - Task 12, full-pipeline Playwright journey (`ee1fc66`, `66ca851`)

- Cross-module string-named FK targets (`ForeignKey("projects.id")` etc.) resolve
  lazily, and nothing asserts that the declaring model module loads its targets'
  modules: the e2e's worker process - which imports only the ingestion chain, never
  the API routers - failed every chunk insert with `NoReferencedTableError` because
  `app.projects.models` had never registered there. Fixed per declaration site
  (`66ca851`: ingestion -> projects + sources, projects -> identity, sources ->
  projects). A cheap architecture test - after importing each model module alone,
  every FK target table must be present in `Base.metadata` - would catch the next
  cross-module FK automatically.


## 2026-10-09 - deferred minors in `fix-deferred-minors-2`, kept open by its final review

- `revoke_token` calls `on_conflict_do_nothing()` without a conflict target, so the
  SQL suppresses violations of every unique constraint on `revoked_tokens` while the
  comment names only the jti primary key; pass `index_elements=[RevokedToken.jti]`
  (from commit `c9942f7`).