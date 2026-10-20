# Backlog

Follow-ups and consciously deferred findings. The S0/S1 review's deferred minors were
all resolved on 2026-10-08 (in the `fix-deferred-minors` branch, merged to master).
The deferred minors from the 2026-10-07 review-feedback session were all resolved on
2026-10-09 in the `fix-deferred-minors-2` branch.


## 2026-10-20 - S5 answer and chat (`s5-answer-chat`)

Residuals from the 2026-10-20 whole-branch review of the S5 answer slice
(`../specs/2026-10-20-s5-answer-chat-design.md`, its plan
`../superpowers/plans/2026-10-20-s5-answer-chat.md`), plus this review-fix wave:

- `c935e14` - whitespace-only `groq_api_key` values passed the validator until this fix
  wave; the check now strips the key before rejecting it.
- `79335bc` - the Groq `LLMError` tests never assert the chained `__cause__` keeps the
  real transport or body error visible in the server log.
- `79335bc` - the `get_llm_provider` factory's groq arm has no direct factory test; a
  focused test would pin the settings-to-provider wiring.
- `79335bc` - `groq_api_key` is a plain `str`; a `SecretStr` would match the
  `jwt_secret`/`s3_secret_key` precedent for credential settings.
- `79335bc` - `get_llm_provider` builds a fresh `httpx.Client` per answer request and
  never closes it; S6 (real providers + API keys) should own the provider lifecycle.
- `dd76d6b` - `test_rerank_true_accepted_and_ignored` compares omitted-vs-`true` instead
  of `false`-vs-`true`; the status codes are asserted as of this fix wave, but the
  full-body equality caveat stays.
- `48df074` - the ChatPanel sources tests assert collapsed accordion details with
  `toBeInTheDocument`, which stays green because MUI keeps collapsed details mounted;
  assert `aria-expanded`, or not-then-visible, instead.
- `48df074` - Enter submits during IME composition; guard the keydown handler with
  `!event.nativeEvent.isComposing`.
- `48df074` - focus is lost while the input is disabled during a request; consider
  refocusing the input when the request settles.
- `26670c9` - a pinned Ask tab could end up disabled if `hasReadyUpload` later flips
  false (no current flow does that; revisit with delete/reprocess).
- `26670c9` - the panels lack `role="tabpanel"`/`aria-labelledby` wiring and the Tabs
  lack `aria-controls`.
- `84ae13d` - `origin` is a plain `str`; a `Literal["direct", "answer"]` alias would
  catch typos in the query-log marker.
- `ce8b5aa` - the `Sources (0)` accordion used to render on a canned empty answer;
  fixed this wave: the Sources accordion renders only when `chunks.length > 0`.
- `79335bc` - `llm_timeout_seconds` is a per-phase httpx timeout, not a total deadline
  (a connect+read worst case can approach nginx's 60s `proxy_read_timeout`); revisit
  if Groq latency grows.
- `cd80537` - the e2e journey's `/tiny\.pdf/` and `/sample\.docx/` source-row selectors
  assume one chunk per file surfaces in Sources; if fixtures ever yield multiple rows
  per file, Playwright strict mode fails - switch to `.first()` or a count assertion.


## 2026-10-16 - Compose full-stack runtime (`compose-full-stack`)

From the spec (`../specs/2026-10-16-docker-compose-full-stack-design.md`, its section
12) and its plan (`../plans/2026-10-16-docker-compose-full-stack.md`, commits
`295393c`..`e16306f`):

- `ec55c32` - containerized e2e as a CI packaging test: run the existing Playwright
  journey against a composed stack in CI, where databases are disposable. The manual
  compose smoke run (the plan's Task 7) covers the packaging gap locally meanwhile.
- `ec55c32` - the other web test files' MSW handlers still use unprefixed paths
  (`*/auth/register` style); they pass because `*` absorbs the `/api` prefix, and
  `src/test/handlers.ts` (the shared baseline) carries the real paths.
- `e16306f` - the README intro ("backend ... for a RAG MVP") predates the full-stack
  round and undersells the repo (SPA + compose system); cosmetic rewording opportunity.
- `ece6266` - a rendered database URL containing `%` (an escaped password) trips
  ConfigParser interpolation in `set_main_option`; the same edge already exists in
  `scripts/e2e_db.py` and `tests/test_alembic.py` (escape with
  `database_url.replace("%", "%%")` when a real password needs it).
- `ece6266` - the migrate script's unreachable-database test asserts only a non-zero exit;
  asserting the connection-failure line in `stderr` would pin the actual failure mode (it
  would also pass on an import-time crash today).
- `e9c748c` - a bare `/api` (no trailing slash) falls through nginx's `location /api/` to
  the SPA fallback; harmless while no route exists at exactly `/api`, revisit if one appears.
- `e9c748c` - `index.html` is served with no `Cache-Control: no-cache`; nginx's
  ETag/Last-Modified validators mostly cover it, but a redeploy can leave a browser on a
  stale bundle.
- `e9c748c` - nginx carries no `proxy_read_timeout`/`proxy_send_timeout` overrides (60s
  defaults); fine while API requests are short, a watch item for slow synchronous
  endpoints. Resolved for `/answer` on 2026-10-20 in `s5-answer-chat` (spec decision 12):
  `llm_timeout_seconds=30` keeps the provider call inside the 60s proxy budget.

From the 2026-10-16 whole-branch review:

- `ec55c32` - the route-prefix test's docs check misses `include_in_schema=False` routes,
  `Mount`s, and WebSocket routes (none exist today); a note in its docstring, or walking the
  included routers, would pin the blind spot.
- `91c616c` - api/worker/dispatcher repeat the same three-variable environment block; an
  `x-backend-env` anchor would keep new settings from drifting between them.
- `91c616c` - the long-running app services carry no `restart:` policy (the infra services
  predate this round without one too): a crashed worker or dispatcher leaves uploads queued
  with no signal (neither has a healthcheck); `restart: unless-stopped` is the cheap fix.
- `e16306f` - the README has no "wait for healthy" pointer (`docker compose ... ps`) before
  the first upload, and no `logs one-off-initialization` pointer for diagnosing a failed
  migration; both are one-liners.
- `e9c748c` - a missing hashed asset answers `index.html` with 200 (the SPA-fallback trap);
  `location /assets/ { try_files $uri =404; }` if it ever matters. The `rag-backend`/`rag-web`
  image tags are project-global (two compose projects overwrite each other's tags) - covered
  by the machine-global runbook note, recorded here for completeness.


## 2026-10-14 - S3 review fixes (`s3-upload-ingestion`)

The pre-merge review-fix round (`../plans/2026-10-14-s3-review-fixes.md`) resolved the
2026-10-13 deferred minors it listed; the entries below survived it. Carried entries
keep their introducing commit links.

Carried from the 2026-10-13 whole-branch review:

- `70cc8f3` - a fixed dev-only `rpc_secret` is committed in `deploy/garage.toml` (required
  for boot, same fixed-dev credential pattern as compose, must never reach a real
  deployment). The garage healthcheck this note originally flagged was added by `91c616c`.
- `4359933` - the pytest suite's warnings (Starlette/httpx deprecation, short test JWT
  HMAC keys) grew from 56 to 73 instances with the new test modules; a pristine-output
  cleanup pass (filterwarnings or test-secret length) is legitimate backlog work.
- `785c59b` - stub parser: the unsupported-suffix `ParseError` branch and multi-page /
  blank-page PDF behavior are untested; factories live in `providers/__init__.py` so any
  `app.providers` import eagerly loads pypdf/python-docx (revisit when real providers
  arrive in S6).
- `0ae199e` - chunker: the hard-split windows' heading context and flush ordering are
  untested; the `stride < 1` ValueError guard is untested; negative `overlap_tokens`
  silently drops words; a heading `level <= 0` would corrupt the heading-stack slice
  (unreachable with the stub parser; note for the S6 Unstructured swap).
- `02cf513` - storage: the key-format test mirrors the implementation's f-string shape;
  a mid-stream protocol drop can surface as a raw urllib3 exception past the
  `StorageUnavailableError` boundary in some botocore versions.
- `347efdc` - the `node-buffer.d.ts` ambient typing will collide if `@types/node` lands
  in the web tsconfig.
- `ee1fc66` - e2e: the journey's intermediate tiny.pdf row assertion exceeds the
  brief's literal shape (diagnosis aid only); stderr-wait webServer entries cannot
  detect an orphaned consumer left by a hard-killed previous run.
- `4359933` mixed the FK-index test fix into the schema commit, and `e3f24cc` is its
  fixup; history is left as is.
- Final-review extra (`3b80c5a`): during a Try-again refetch with no cached data the
  skeleton briefly replaces the error card.
- `0ae199e` - `chunk_elements` does not skip whitespace-only paragraph elements: one
  arriving between paragraphs would leave a stray `\n\n` separator in the joined chunk
  text, and one arriving alone would be emitted as an empty chunk. Unreachable today -
  the stub parser strips and skips empty text before elements reach the chunker - but
  worth hardening when real Unstructured replaces the stub at S6.

New deferrals from the 2026-10-14 review fixes:

- Upload body size is enforced only after Starlette spools the body; a Content-Length
  guard or a proxy limit is needed before any exposed deployment.
- Prefork readiness: `task_reject_on_worker_lost` with a delivery limit for embed.
- `worker_prefetch_multiplier=1` and separate worker processes per queue before S6's
  network providers.
- Embed re-delivery re-embeds every chunk (filter `embedding IS NULL` or skip
  non-`indexing` runs before paid providers).
- The identical-version backstop marks a run `ready` against a document that may be
  half-embedded or inactive (S7).
- A partial unique index allowing one in-flight run per item, together with the S7
  sweep; the sweep must also cover `queued` runs whose event was published.
- Outbox attempts cap, dead-lettering, and published-row retention (S7).
- A crash between the Garage PUT and the write transaction's commit orphans the stored
  object (no delete path in S3); fold the orphan sweep into the S7 stale-run sweep.
- S4 retrieval notes: HNSW `ef_search` and `iterative_scan` tuning stays deferred (ruled
  again at the 2026-10-19 S4 review). The ceiling is structural, not just tuning: the HNSW
  scan returns at most `hnsw.ef_search` rows (default 40) *before* the `project_id` filter,
  so the vector leg can never fill its `retrieval_candidates_per_retriever=50` budget at
  scale, and a small tenant whose chunks miss the global top 40 gets an empty vector leg
  with no error - an isolation-sensitive cap. Fix with `SET LOCAL hnsw.ef_search =
  <candidates>` plus `SET LOCAL hnsw.iterative_scan = strict_order` in the leg (about two
  lines, now possible since the image is pinned). The other two notes landed with S4:
  `embedding IS NOT NULL` filters both retrieval legs (`f13e0c2`), and the
  `pgvector/pgvector` image tag is pinned to `0.8.7-pg17` (`5190196`).
- S6: record `embedding_model` per vector; prefer a side-by-side column over an
  in-place dimension change.
- S9: the listing must aggregate multi-item sources, and source-level sync failures
  need a home.
- Same-name uploads differing only in case are distinct files.
- The parser, service, and chunker all guard empty documents with different messages
  (consolidate at S6).
- Viewer upload 404 copy, a live region for status changes, and the stale-data snackbar
  parity with `ProjectsPage`.
- The UI says "documents" for uploads while the backend's `documents` are parsed
  versions.
- A two-session `SKIP LOCKED` dispatcher test, and closing each test's Celery app.
- Time-ordered `uuid7` primary keys (house-wide).
- Optional cheap checks: `jsonb_typeof(heading_path) = 'array'`; `NormalizedElement.type`
  as a `Literal` before S6's Unstructured swap.
- Compose ports bind every interface; the production validator ignores the `guest`
  broker URL.


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
- 2026-10-12 - Changing the embedding model or dimension (S6 swaps the stub constant
  `STUB_EMBEDDING_DIM` for Voyage) invalidates every stored vector, so it needs
  re-embedding, not just a dimension migration: clear `chunks.embedding`, re-enqueue a
  `document_ready_for_embedding` outbox event per existing document, and let uploads
  travel indexing -> ready again. Re-embedding can run from persisted `chunks.text`, so
  no re-parse is needed. The S3 spec adds the matching `STUB_EMBEDDING_DIM` comment
  (dimension changes require an Alembic migration); this re-embedding flow is the
  deferred half.
- 2026-10-12 - S7 needs stuck-run recovery (S3 spec section 10 risk table): a worker
  crash mid-run leaves its `ingestion_runs` row - and the derived upload status -
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


## 2026-10-09 - deferred minors in `fix-deferred-minors-2`, kept open by its final review

- `revoke_token` calls `on_conflict_do_nothing()` without a conflict target, so the
  SQL suppresses violations of every unique constraint on `revoked_tokens` while the
  comment names only the jti primary key; pass `index_elements=[RevokedToken.jti]`
  (from commit `c9942f7`).