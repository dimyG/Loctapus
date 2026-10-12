# S3 - Upload & Ingestion (stub providers) + Upload UI - Design

Date: 2026-10-12
Status: Approved design; ready for the implementation plan (two review rounds applied,
both 2026-10-12; the second round's changes say so where they amend first-round text).
Source of truth: `../../2026-10-06-initial_rag_mvp_agent_project_context.md` (the "MD") and
`2026-10-06-rag-mvp-slices-design.md` (the "slices spec"). Where those disagree with this
document on S3 topics, this document wins; where this document is silent, they govern.

## 1. Context

S3 is the re-cut upload+ingestion slice (slices spec decision 6): the full offline ingestion
pipeline - PDF/DOCX upload -> Garage (replacing MinIO, section 3.2) -> Celery ingestion
(stub parse -> normalize -> chunk) -> chunks + outbox event in one transaction -> dispatcher
-> `embed` queue -> stub embeddings -> HNSW/GIN indexes - plus the frontend project page
with upload and processing status. Retrieval is S4.

Done-when (slices spec section 2): upload a real PDF from the browser and watch it reach
`ready` - fully offline. S0-S2 are implemented on `master`; every slice from S2 on pairs
backend + frontend (slices spec decision 5), so S3 ships the API and the UI together.

Environment (verified 2026-10-06, storage status re-verified 2026-10-12): Windows 10;
Docker 29.6.2 + Compose v5.3.1; Python 3.14 venv at `.venv`; Node 24.14.1 / npm 11.20.0.
RabbitMQ 3.13 (compose) is already provisioned by S0. MinIO is replaced by Garage in this
slice: the MinIO community edition reached end-of-life in February 2026 (backlog item,
resolved here).

## 2. Decisions (2026-10-12 design round, amended by the 2026-10-12 spec review rounds)

1. **Garage replaces MinIO now.** Chosen from the backlog's candidates (Garage vs
   SeaweedFS) for a single-container footprint, minimal config, and active maintenance.
   The `minio` service, `miniodata` volume, and the EOL TODO comment are removed
   (dev-only data). Provisioning is compose-only - no bootstrap script (section 3.2).
2. **All pipeline triggers go through the transactional outbox.** The upload transaction
   writes a `source_item_ingestion_requested` event; the API process never touches
   RabbitMQ. No commit-then-publish gap, and one mechanism carries both pipeline
   triggers (MD section 18). Lossless needs two delivery details the design round did
   not spell out (section 5.2): the dispatcher marks `published_at` only after a broker
   publisher confirm, and the worker acks late (`task_acks_late`) - so a crash between
   commit and confirmed publish re-publishes (at-least-once), and a crash mid-task
   re-delivers. Second round, stated honestly: late acks only rescue `embed`, whose
   in-place vector updates absorb re-delivery (section 5.4); a re-delivered *ingestion*
   message is dropped by its claim guard and the run stays non-terminal - the accepted
   stuck-run cost (section 10). The ingestion leg is at-least-once into the claim guard,
   not into execution.
3. **The S3 outbox dispatcher is a standalone polling process** (review amendment; the
   design round had Celery Beat, whose CLI refuses `-B` outright on Windows: "-B option
   does not work on Windows"): a plain `while True: dispatch_batch(); sleep` loop over
   unpublished rows every `outbox_poll_interval_seconds` (default 1s, section 5.2). For
   S3 that is the whole scheduling story - a clock-driven dispatch task buys nothing
   over a sleep loop, drags in a per-environment schedule file, and would pile up tick
   messages whenever the worker is down. **S7's sync scheduler is deliberately not
   decided here** (second round): the slices spec's S7 row still says "Celery Beat sync
   polling", and S7's own design round picks between the two real options - extending
   this same dispatcher loop, or running `celery beat` as its own process (only the
   *embedded* `-B` form is refused on Windows; a standalone beat process runs fine).
   S3 must not preclude either.
4. **The stub embedding is a deterministic hash-bag**: lowercase word split, each token
   sha256-hashed into one of `STUB_EMBEDDING_DIM` buckets with a sign bit, L2-normalized.
   Same text always yields the same vector - idempotent re-runs and reproducible tests -
   and cosine similarity behaves like soft lexical overlap so S4 retrieval is meaningful
   fully offline. Empty text yields the zero vector (documented). The dimension is a
   provider constant (`STUB_EMBEDDING_DIM = 384`), not a setting: migrations hardcode the
   literal, and the startup guard (decision 9) cross-checks the constant against the
   catalog. The design round's `RAG_EMBEDDING_DIM` setting is dropped - it was fake
   configurability, since the column moves only via a migration anyway.
5. **Token counting for chunking is a documented estimate** (words x 4/3); no tokenizer
   dependency. Settings stay in token units (MD section 9): target 600, max 1000,
   overlap 80.
6. **Full-pipeline Playwright e2e**: the journey runs against the real worker (solo
   pool) plus the dispatcher and asserts upload -> `ready` through the browser, covering
   both stub parsers via the true broker path. Chosen over split coverage at the design
   round; topology amended by the review (no Beat, decision 3).
7. **Deferred decisions finalized** (slices spec section 5 table): #3
   `documents.normalized_content` JSONB holds the elements array; #4 the embedding
   dimension - the provider constant `STUB_EMBEDDING_DIM` (stub: 384, decision 4) with
   the migration + re-embedding comment (section 3.3); #7 object key
   `raw/{project_id}/{source_item_id}/{content_hash}/{filename}`; #9
   replace-only-after-success - decided now, with the deletion logic itself shipping in
   S7 (no replacement path exists in S3: each upload creates a new source).
8. **`ingestion_runs` keys on `source_item_id` only** (design-round amendment; the MD
   section 27 draft had `source_id`, which is one join away through `source_items`).
   `created_at` (`func.now()`, set by the inserting transaction - one row per
   transaction, so no ties) orders "latest run" for the derived source status
   (decision 12).
9. **Startup dimension guard (worker)**: at boot the worker compares the *selected
   provider's* `dimension` attribute - the stub's `STUB_EMBEDDING_DIM`; giving
   `EmbeddingProvider` a `dimension` keeps the guard correct in S5 when Voyage replaces
   the stub - against the actual `chunks.embedding` catalog type, and refuses to start
   on mismatch with an actionable message (section 4.3). The `worker_init` handler
   raises `SystemExit`, not a plain `Exception`: Celery's signal dispatch catches
   `Exception` and logs it, which would leave the worker running (section 4.3). S3
   wires it into the worker only: the TestClient cannot reach an API-startup check
   without an injectable engine (the module-level `SessionLocal` points at the dev
   database), so the API-side check lands in S4 with the retrieval path that actually
   needs it.
10. **The re-embedding follow-up is recorded in the backlog** (2026-10-12): swapping the
    embedding model or dimension invalidates stored vectors; re-embedding runs from
    persisted `chunks.text` (no re-parse), clearing embeddings and re-enqueueing one
    outbox event per document.
11. **Item identity is the filename; the content hash is the version fingerprint**
    (review amendment): `source_items.external_id` is the stable identity of the item
    inside its source (MD section 27: upload id, page URL, Drive file id) - the uploaded
    filename - with `unique(source_id, external_id)`, so a re-uploaded changed file is
    recognized as the *same item with new content* and S7's replace-only-after-success
    path has something to replace. `content_hash` alone tracks the content version; the
    design round's `external_id = sha256(bytes)` made identity change with content,
    which silently breaks that path and duplicates `content_hash`.
12. **Source status is derived, not stored** (review amendment): status lives on
    `ingestion_runs` only (the check constraint); the sources list endpoint joins each
    source to its item's latest run (`created_at`) and returns that status. No mirrored
    column means no double writes to drift, no cross-module write discipline, and S9
    defines multi-item aggregation in one query instead of reinventing a stored rollup.
13. **Event payloads carry the ids consumers act on** (review amendment):
    `source_item_ingestion_requested` payloads carry `source_item_id` +
    `ingestion_run_id` + `raw_object_key` + `content_hash` (second round: the last two
    pin each run to the file *version* it was created for - an S7 re-upload rewrites
    the item's latest key, and an older queued run must fetch its own bytes, never the
    newer ones); `document_ready_for_embedding` payloads carry `document_id` +
    `ingestion_run_id`; and every run transition is `UPDATE ... WHERE id = :run_id AND
    status = :expected`. Claims stay per-run when S7 adds per-attempt runs, and
    re-delivery of a finished run is a no-op instead of re-claiming a queued sibling.
14. **One broker vhost per environment** (review amendment): dev (`/`), pytest
    (`rag_test`), and e2e (`rag_e2e`) each get their own RabbitMQ vhost inside
    `broker_url`, created by the same bootstraps that build each database. Without
    them a running dev worker consumes the e2e run's ingestion messages and skips them
    against the dev database, hanging the journey - the databases already have this
    isolation; the design round forgot to give the broker the same. Second round adds
    the two missing plumbing details. Creation: through the management HTTP API compose
    already exposes on 15672 - `PUT /api/vhosts/{name}` then
    `PUT /api/permissions/{name}/guest` with `{"configure": ".*", "write": ".*",
    "read": ".*"}` (a newly created vhost grants no permissions by default, and
    `guest` needs them to connect); both calls are idempotent and repeat-safe.
    Reaching the code: the vhost only isolates if the app under test is built from the
    same per-environment URL, so `make_celery_app(*, broker_url)` (section 3.4) is the
    broker twin of `make_engine`, the dispatcher takes its app as a keyword-only
    argument, and the pytest fixtures read `RAG_TEST_BROKER_URL` (default
    `amqp://guest:guest@localhost:5672/rag_test`) beside `RAG_TEST_DATABASE_URL` -
    the module-level default app points at the dev vhost exactly as `SessionLocal`
    points at the dev database.

## 3. Dependencies and infrastructure

### 3.1 Backend dependencies (`backend/pyproject.toml`)

| Package | Use |
|---|---|
| `celery>=5.6` | worker + dispatcher (RabbitMQ broker; kombu/amqp ship with it). 5.6, not 5.5: Python 3.14 support landed there (5.5 stops at 3.13) |
| `boto3` | Garage/S3 client (path-style addressing) |
| `pgvector` | SQLAlchemy `Vector` type for `chunks.embedding` in the model and the migration |
| `python-multipart` | multipart parsing for the upload route - FastAPI refuses to serve a route declared with `UploadFile` without it |
| `pypdf` | stub PDF parser |
| `python-docx` | stub DOCX parser |

No Celery result backend: task outcomes live in Postgres (`ingestion_runs`); Celery moves
messages only. Second round: `mypy app tests` (strict) also needs stubs for the untyped
third parties - `celery-types` and `boto3-stubs[s3]` join the dev extras (or a narrowly
scoped mypy override per package, whichever the implementation finds smaller).

### 3.2 Compose: Garage replaces MinIO (`deploy/docker-compose.yml`)

- Service `garage`: `dxflrs/garage` (version pinned at implementation), config mounted
  from `deploy/garage.toml` (replication_factor 1, S3 API on `0.0.0.0:3900` with
  `s3_region = "garage"`, admin API on 3903), named volumes for meta and data. Ports
  3900 + 3903. Second round, checked against the v2.3.0 source: the command must be
  the absolute `/garage server --single-node --default-bucket` - the image is
  `FROM scratch` with no `PATH` and the binary lives at `/garage` (the docs' bare
  `garage server ...` would not resolve).
- The `minio` service, its `miniodata` volume, and the EOL TODO comment are removed.
  `docker compose up` now yields db + RabbitMQ + Garage.
- **No bootstrap script** (review amendment): Garage v2.3.0+ self-provisions. The
  service command is `/garage server --single-node --default-bucket`, and compose passes
  fixed dev credentials through `GARAGE_DEFAULT_ACCESS_KEY` / `GARAGE_DEFAULT_SECRET_KEY`
  / `GARAGE_DEFAULT_BUCKET=rag-dev` - the same fixed-credentials-in-compose pattern the
  `db` service already uses for `rag`/`rag`. The settings defaults mirror the compose
  values (section 3.3), so dev, pytest, and e2e need no `.env` writing step at all.
  Pytest and e2e share the single Garage and its `rag-dev` bucket with dev: object keys
  carry UUIDs and content hashes, so environments cannot collide.
- Garage's startup order and failure modes (second round, from the v2.3.0 source):
  `garage server` finishes the single-node layout and the default key/bucket *before*
  the S3 listener starts, so no client ever sees a half-provisioned Garage; restarts
  with an existing layout and an unchanged secret are safe. But a `GARAGE_DEFAULT_*`
  key that already exists with a *different* secret makes startup fail - so changing
  `GARAGE_DEFAULT_SECRET_KEY` after first start bricks the service until the metadata
  volume is wiped; the README runbook says so (section 9). The compose values must
  satisfy Garage's import validation: key id >= 8 chars of `[A-Za-z0-9._-]` (the planned
  `rag-dev-key` qualifies), secret >= 16 printable-ASCII chars.
- `garage.toml`'s `s3_region` must equal the `s3_region` setting default: Garage rejects
  S3 calls signed for any other region with `AuthorizationHeaderMalformed`.

### 3.3 Settings additions (`app/core/config.py`, `RAG_` prefix)

| Setting | Default | Use |
|---|---|---|
| `broker_url` | `amqp://guest:guest@localhost:5672//` | Celery broker; the trailing segment is the vhost - dev `/`, pytest `rag_test`, e2e `rag_e2e` (decision 14) |
| `s3_endpoint` | `http://localhost:3900` | Garage S3 API |
| `s3_access_key` / `s3_secret_key` | `rag-dev-key` / the compose `GARAGE_DEFAULT_SECRET_KEY` value | credentials; defaults mirror compose (section 3.2), so no bootstrap writes `.env` |
| `s3_region` / `s3_bucket` | `garage` / `rag-dev` | client config; region must equal `garage.toml`'s `s3_region` (section 3.2) |
| `parser_provider` / `embedding_provider` | `stub` / `stub` | provider selection |
| `chunk_target_tokens` / `chunk_max_tokens` / `chunk_overlap_tokens` | 600 / 1000 / 80 | chunker budgets |
| `embedding_batch_size` | 64 | embed batching |
| `outbox_poll_interval_seconds` / `outbox_batch_size` | 1.0 / 20 | dispatcher sleep / rows per batch |
| `max_upload_mb` | 25 | upload validation |

`STUB_EMBEDDING_DIM` (in `app/providers/stub_embeddings.py`) carries an inline comment:
changing it requires an Alembic migration that re-types `chunks.embedding` (migrations
hardcode the literal, never a runtime value) **and** re-embedding every stored chunk
(backlog 2026-10-12; re-embedding runs from `chunks.text`, no re-parse needed).

### 3.4 Module layout (slices spec section 3 map)

```
backend/app/
  core/         session_scope helper (db.py)                  # Base stays alone in models.py
  sources/      models.py, router.py, schemas.py, service.py    # upload + list
  ingestion/    models.py (documents, chunks, ingestion_runs), service.py, chunking.py
  storage/      service.py                                       # boto3 put/get
  providers/    base.py (Parser, EmbeddingProvider, NormalizedDocument),
                stub_parser.py, stub_embeddings.py
  outbox/       models.py, events.py                            # ORM + event -> queue map
  workers/      celery_app.py, tasks.py, dispatcher.py         # app, thin tasks, poll loop
```

Queue names `ingestion` / `embed`, event types, their payloads, and the event ->
(task, queue) routing map all live in `app/outbox/events.py` (second round: queue names
moved over from `app/workers/celery_app.py`, so the API process - which only writes
events - never imports Celery at all; the workers import the names from there). The
Celery app is constructed through `make_celery_app(*, broker_url)` in
`app/workers/celery_app.py` - the broker twin of `make_engine` - and the dispatcher
takes its app as a keyword-only argument, so tests point both at the `rag_test` vhost
instead of the module-level dev default (decision 14). Celery tasks are thin wrappers
over `app/ingestion/service.py` functions (keyword-only session arguments), so
pipeline logic tests without Celery. Workers get sessions through a `session_scope`
context manager in `app/core/db.py` (request-scoped `get_db` does not apply outside
HTTP). `alembic/env.py` imports the new model modules for autogenerate.

### 3.5 Runbook (dev + e2e)

```
docker compose up -d                    # db + rabbitmq + garage (deploy/)
uvicorn app.main:app                    # API
celery -A app.workers.celery_app worker --pool=solo -Q ingestion,embed
python -m app.workers.dispatcher        # outbox polling loop (decision 3)
```

Prefork is unsupported on Windows; `--pool=solo` is the supported dev pool. So is
embedded Beat - celery's CLI refuses `-B` outright on Windows - hence the dispatcher as
its own plain process (decision 3).

## 4. Data model

### 4.1 Tables (one Alembic migration; house style: client-generated UUID pk,
`DateTime(timezone=True)` with `func.now()` server defaults)

```
sources          id, project_id -> projects ON DELETE CASCADE, type (check 'upload'),
                 created_at
source_items     id, source_id -> sources ON DELETE CASCADE, external_id (the uploaded
                 filename; unique(source_id, external_id)), filename, content_type,
                 size_bytes, content_hash (sha256 of the raw bytes), raw_object_key,
                 created_at
documents        id, source_item_id -> source_items ON DELETE CASCADE, content_hash
                 (sha256 of the canonical normalized JSON - title + elements + metadata only,
                 never ids or timestamps: those inside the hashed JSON make every hash
                 unique and the `unique(source_item_id, content_hash)` duplicate guard dead),
                 raw_object_key (copied from the item; MD section 27), normalized_content
                 JSONB (the full normalized
                 document: title, elements, metadata), created_at,
                 unique(source_item_id, content_hash)
chunks           id, project_id -> projects ON DELETE CASCADE (intentional
                 denormalization for the retrieval hot path - rationale comment in the
                 model, MD section 27), document_id -> documents ON DELETE CASCADE,
                 position, text, heading_path JSONB (string array), chunk_type (check
                 'text'), chunk_metadata JSONB - only the Python *attribute* is renamed
                 (`metadata` is reserved on SQLAlchemy declarative models); the column keeps
                 the MD's `metadata` name, which S4's SQL will query - content_hash
                 (sha256 of text), embedding vector(384) NULL until embedded,
                 search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english',
                 text)) STORED, unique(document_id, position)
ingestion_runs   id, source_item_id -> source_items ON DELETE CASCADE, document_id ->
                 documents ON DELETE SET NULL, status (check 4.2), created_at,
                 started_at (set by the claim), finished_at, error
outbox_events    id, event_type, aggregate_type, aggregate_id (uuid), payload JSONB,
                 created_at, published_at (nullable), attempts (default 0), last_error;
                 partial index on created_at WHERE published_at IS NULL
```

- `ingestion_runs` keys on `source_item_id` only (decision 8); `created_at` defines the
  latest run per item (no ties: one row per transaction).
- No `sources.status` column (decision 12): the list endpoint derives each source's
  status from its item's latest run, so the schema has exactly one stored status.
- File metadata (filename, content type, size) describes one content *version*, so it
  lives on `source_items` (decision 11), not in a source-level config blob; upload
  sources carry no connector config at all - `sources.config` arrives in S9 when
  website sources need root URLs, instead of shipping unused now.
- `sync_interval`, `last_sync_at`, `url`, `remote_version`, `last_seen_at`,
  `deleted_at`, and per-run `attempt` have no S3 behavior; they arrive with S7/S9 when
  their semantics exist, not as dead columns now (section 11).
- Chunk `chunk_metadata` for S3 carries `{"filename": ...}` copied from the item - the
  citation-ready minimum S4's retrieval response will surface.
- Hashes: raw-bytes sha256 -> `source_items.content_hash` (the version fingerprint);
  canonical normalized JSON (sorted keys) sha256 -> `documents.content_hash`; chunk-text
  sha256 -> `chunks.content_hash`. `external_id` stays content-independent (decision 11).
  Second round, the scope of the document hash (the 4.1 block says it too): title +
  elements + metadata only - never ids or timestamps, which would make every hash unique
  and the `unique(source_item_id, content_hash)` duplicate guard dead on arrival.
- Every FK cascades, so project deletion stays a plain `DELETE`: projects -> sources ->
  source_items -> {documents -> chunks, ingestion_runs}; `chunks.project_id` cascades
  along the denormalized path; `ingestion_runs.document_id` is SET NULL so run history
  survives document replacement (S7). Raw Garage objects under the deleted project's
  key prefix stay behind - harmless, no delete path in S3. Second round: any ORM
  relationship grown across these tables (e.g. a `Project.sources` convenience mapping)
  declares `passive_deletes=True` mirroring its `ondelete` rule, so deleting a project
  issues one `DELETE` and lets the database cascade - instead of SQLAlchemy loading the
  children to null or delete them client-side, which wastes the round trips and would
  fight the SET NULL on `ingestion_runs.document_id`.
- Chunks are FTS-searchable the moment they commit, before embeddings and `ready` land;
  activation semantics (only the replacement document visible to retrieval) are S7
  scope.

### 4.2 Status machine (MD section 6)

`queued | fetching | processing | indexing | ready | failed`, as a check constraint on
`ingestion_runs.status` - the only stored status; the sources list derives (decision 12).
Every transition is `UPDATE ... WHERE id = :run_id AND status = :expected`; zero rows
updated means a duplicate or stale delivery -> ack, no-op (decision 13).
Second round, `expected` is concrete: the status the writing task last set -
`fetching` or `processing` for an ingestion failure, `indexing` for an embed failure -
so a stale delivery can never clobber a newer state.

| Status | Set by |
|---|---|
| `queued` | upload transaction (run row created) |
| `fetching` | ingestion task claim (`WHERE status = 'queued'`) |
| `processing` | ingestion task, after raw bytes are fetched |
| `indexing` | the document+chunks+outbox commit (also links `document_id`) |
| `ready` | embed task, after vectors are updated (`WHERE status = 'indexing'`) |
| `failed` | either task on error (error text on the run; no auto-retries in S3 - S7) |

### 4.3 pgvector + indexes in the migration

- `CREATE EXTENSION IF NOT EXISTS vector`; the downgrade drops it, and the migration
  downgrade test (mirroring the citext one) asserts it.
- `chunks.embedding vector(384)` - the literal `STUB_EMBEDDING_DIM`, hardcoded: a
  migration never reads a runtime value, so one revision builds one schema in every
  environment; changing it requires a new migration (decision 4).
- HNSW: `USING hnsw (embedding vector_cosine_ops)`; GIN: `USING gin (search_vector)` -
  both created with this slice's schema so S4's retrieval queries rely on them.
- `search_vector` is a `GENERATED ALWAYS ... STORED` column (section 4.1), so the
  formula lives in one place and every write path gets it for free; on this Postgres
  17, `ALTER COLUMN ... SET EXPRESSION` lets S4 reweight it in one migration that
  recomputes every row.
- FK indexes where no composite unique already covers the leading column (second round,
  trimming the blanket list): `sources.project_id`, `chunks.project_id` (what retrieval
  filters on), `ingestion_runs.document_id` (the SET NULL target), plus
  `ingestion_runs (source_item_id, created_at)` - one composite serving both the item FK
  and the latest-run lookup (decision 12). Skipped as redundant: `source_items.source_id`,
  `documents.source_item_id`, and `chunks.document_id` lead their composite unique
  constraints (a leading column is served by the constraint's index, migration 0004's
  house reading), and an index on `chunks.document_id` would tax every chunk insert.
  `test_foreign_key_columns_are_indexed` grows the same columns - after fixing its own
  pre-existing hole (second round, section 8): it must compare each index's *leading*
  column only, because today it collects every column of every index, unique-constraint
  indexes included, so dropping `ix_project_team_roles_team_id` would still pass.
- **Startup guard (worker only in S3, decision 9)**: compare the column's catalog type
  (`format_type` over `pg_attribute`, parse the dimension) with the selected provider's
  `dimension` (the stub's `STUB_EMBEDDING_DIM`; decision 9) and fail fast, e.g.
  "chunks.embedding is vector(384) but the selected provider emits 512; changing the
  dimension requires an Alembic migration". This prevents a cryptic psycopg insert
  failure deep in the embed path after chunks are already committed. The check runs in
  a `worker_init` signal handler that raises `SystemExit` - not a plain `Exception`,
  which Celery's signal dispatch catches, logs, and swallows, leaving the worker booted
  (second round). Unit tests cover the comparison against matching and mismatching
  catalog fixtures *and* the handler's refusal to boot.

## 5. Ingestion pipeline

### 5.1 Upload flow (`POST /projects/{project_id}/sources`)

1. Authorization: `get_project_for_user_with_role(minimum_role="editor")`; None -> 404
   "project not found" (house convention: 404 hides both missing and forbidden).
   Viewer-role and public-project users cannot upload.
2. Validation (before reading the body): extension `.pdf`/`.docx`, non-empty, and
   `UploadFile.size` <= `max_upload_mb` - the size check skips reading the bytes,
   which matters at the 25MB cap. Violations -> 422 with a friendly detail. The stored
   filename is sanitized first (basename only; no separators, traversals, or control
   characters; length capped): it is both display data and part of the storage key.
3. sha256 the bytes; build the key
   `raw/{project_id}/{source_item_id}/{content_hash}/{filename}` (decision #7). House
   UUIDs are client-generated, so the key is buildable before any row exists.
4. Copy the ids the rest of the flow still needs (project id, user) into locals, then
   end the request's read transaction (the auth dependency opened one) with `commit()` -
   not `rollback()` (second round) - and PUT the object to Garage: raw persisted before
   parsing, and no DB transaction open across the storage call (MD section 30). Why
   `commit()` and pre-copied locals: the test harness wraps each test in a savepoint, so
   `rollback()` unwinds to it and silently discards uncommitted setup rows the test added
   (a granted role, a seeded user) - a mid-test upload then 404s on its next request; and
   after a rollback, touching any loaded instance (even reading `project.id`) implicitly
   opens a *new* transaction, which then stays open across the Garage PUT. An API test
   pins this down (section 8): the storage client is patched to capture the session's
   transaction state during the PUT, and it must read "no transaction open".
   Storage failure -> 503 with a retryable message, no rows written; an object
   orphaned by a failed later commit is harmless (no delete path in S3).
5. One transaction: `sources` (type `upload`) + `source_items` (identity + file
   metadata + `raw_object_key`, decision 11) + `ingestion_runs` (`queued`) +
   `outbox_events` row `source_item_ingestion_requested` (aggregate source_item;
   payload `{"source_item_id": ..., "ingestion_run_id": ..., "raw_object_key": ...,
   "content_hash": ...}` - decision 13, second round: the run consumes its own file
   version, immune to an S7 re-upload rewriting the item's latest) -> commit
   -> 201 `SourceOut`.

### 5.2 Outbox dispatcher (standalone process, `app/workers/dispatcher.py`)

- A plain loop, no Celery Beat (decision 3): every `outbox_poll_interval_seconds`, one
  batch - select unpublished rows (`outbox_batch_size`, ordered `created_at`, `FOR
  UPDATE SKIP LOCKED`), publish each via the injected app's `send_task` (decision 14)
  to the queue routed from `event_type` through the `app/outbox/events.py` map, set
  `published_at` on success; on failure `attempts += 1` + record `last_error`, retried
  next tick.
- Second round, transaction shape: one *short* transaction per batch - select, publish,
  mark, commit - and nothing held while sleeping; a dispatcher idling inside a
  transaction would block the e2e suite's `TRUNCATE` between tests and sit on locks
  between ticks. A broker connection error ends the batch there (rows not yet published
  keep their `attempts`/`last_error` bump for the next tick) rather than retrying
  publishes in place under row locks.
- Publishing happens under the row locks on purpose: that is what makes "mark
  published" crash-safe, and SKIP LOCKED lets overlapping dispatcher runs cooperate.
- Durable queues, persistent messages, broker publisher confirms, and worker
  `task_acks_late` (decision 2). Publisher confirms made concrete (second round): the
  app's broker connection sets `broker_transport_options={'confirm_publish': True}`
  (kombu's pyamqp transport), so `send_task` blocks until the broker's `basic.ack`, and
  "set `published_at` only after the broker acknowledges" is a real wait - without
  confirms, a broker-side rejection (e.g. an oversized message) closes the channel
  asynchronously and the publish is lost with no visible error. So a crash between
  publish and mark re-publishes (duplicate) and never loses; a crash mid-task
  re-delivers, and consumers are idempotent (claim guards, decision 13; the embed leg
  absorbs re-delivery, the ingestion leg drops it - decision 2).
- Duplicate publishes are expected (crash between publish and mark, MD section 18).
  Poison events retry indefinitely in S3; backoff/caps are S7 robustness scope.
- Routing (the one map, `app/outbox/events.py`): `source_item_ingestion_requested` ->
  `ingestion`; `document_ready_for_embedding` -> `embed`.

### 5.3 Ingestion task (`ingest_source_item`, queue `ingestion`)

- **Claim guard**: `UPDATE ingestion_runs SET status='fetching', started_at=now() WHERE
  id = :run_id AND status='queued'` - keyed by run id (decision 13), so S7's
  per-attempt runs cannot claim each other. Zero rows updated -> duplicate delivery or
  stale message -> ack, no-op. Missing subject rows -> ack, skip (absorbs stale queue
  messages, e.g. after e2e DB truncation).
- fetching: pull raw bytes from Garage through the storage module, by the
  `raw_object_key`/`content_hash` carried in the event payload (decision 13) - never by
  rebuilding the key from item columns, which an S7 re-upload could have rewritten
  since the run was queued.
- processing: parser provider -> `NormalizedDocument` (title from filename; elements
  `{type, level?, text}`); document `content_hash` from the canonical JSON. A document
  with zero extractable elements (e.g. a scanned PDF) raises a parse error -> run
  `failed` with a clear message.
- chunk: the structure-aware chunker (section 5.5).
- One transaction (MD section 30): document row (links `document_id` on the run) + all
  chunks (`search_vector` generated, `embedding` NULL) + `document_ready_for_embedding`
  outbox row + run -> `indexing` -> commit. No transaction spans storage or provider
  calls - the embed task keeps the same rule: `embed_documents` runs outside any
  transaction and the vector UPDATEs commit per batch (section 5.4).
- Any failure -> run `failed` with the error text; the sources list derives it
  (decision 12). A document-insert conflict on `unique(source_item_id, content_hash)`
  cannot happen in S3 - one item per upload, one run per item, and the claim guard drops
  re-deliveries - but if it ever fires (second round), the run becomes a no-op per MD
  section 19's idempotency rule (identical version already processed: ack, mark the run
  terminal against the existing document - not a `failed`), and the constraint stays
  as the database-level backstop for S7's hardening.

### 5.4 Embed task (`embed_document`, queue `embed`)

- Load document + chunks; batch them (`embedding_batch_size`) through
  `embed_documents`; UPDATE `chunks.embedding` in place - in-place updates make
  duplicate delivery naturally idempotent (deterministic stub: same text -> same vector).
- Then run -> `ready` (`finished_at` set) via a conditional `WHERE id = :run_id AND
  status='indexing'` transition; the sources list derives it (decision 12). Missing
  document -> ack, skip. Errors -> `failed`.

### 5.5 Chunker (`app/ingestion/chunking.py`, replaceable by design)

Structure-aware recursive chunking (MD section 9):

- Walk elements keeping a heading stack; each chunk records its `heading_path`.
- Pack consecutive paragraphs under the same heading until adding the next element
  would exceed `chunk_target_tokens` (estimated words x 4/3); a single element over
  `chunk_max_tokens` hard-splits by words with `chunk_overlap_tokens` overlap. Packing
  stops *at* the target, so the overflowing element starts the next chunk instead of
  enlarging the current one: the invariant is that no emitted chunk ever exceeds
  `chunk_max_tokens`.
- Heading text is recorded in `heading_path` only, never duplicated into chunk text;
  a headings-only document therefore yields zero chunks, which is a parse error per
  section 5.3 (the chunker never silently produces zero chunks).
- Golden-document unit tests cover: heading boundaries, target packing, max enforcement
  with overlap, `heading_path` correctness, tiny document -> one chunk, headings-only
  document -> parse error, and an empty element list -> the chunker raises.

### 5.6 Stub providers (`app/providers/`)

- Interfaces in `base.py`: `Parser` protocol `parse(*, filename, content) ->
  NormalizedDocument`; `EmbeddingProvider` with `embed_documents(texts)` /
  `embed_query(text)` (MD section 10). Selected via settings; the stubs are permanent,
  tested code (slices spec decision 2).
- PDF (pypdf): one paragraph element per page - honest about PDFs carrying no semantic
  structure; `heading_path` stays empty for PDFs. DOCX (python-docx): `Heading N` ->
  heading level N, otherwise paragraph; tables are skipped in S3 - the element model
  carries the types so tables/code arrive with real Unstructured at S5.
- Embedding stub: the deterministic hash-bag (decision 4).

## 6. API surface

| Endpoint | Auth | Behavior |
|---|---|---|
| `POST /projects/{project_id}/sources` | `get_current_user` + editor role | section 5.1; 201 `SourceOut`; 422 validation; 503 storage; 404 house convention |
| `GET /projects/{project_id}/sources` | `get_current_user` + `get_project_visible_to_user` | list newest-first; no pagination in S3 |

`SourceOut = {id, project_id, type, status, filename, created_at}` - house `*Out`
naming, not `SourceRead`. The list joins each source to its (single) item's latest run
(`created_at`; `DISTINCT ON` or lateral) and derives `status` and `filename` from it
(decision 12): each upload source has exactly one item in S3, and S7/S9 generalize the
join only if multiple items ever arrive. Errors use FastAPI's `{detail}` shape like the
rest of the API. Routers handle HTTP only; row creation + listing live in
`app/sources/service.py`.

## 7. Frontend (`web/`)

- New guarded route `/projects/:projectId` (DashboardLayout); `ProjectsPage` project
  names become links to it.
- **ProjectPage**: header with the project name (`GET /projects/{id}`, existing S1
  endpoint) + a back link to `/projects`. **Upload card**: file picker accepting
  `.pdf,.docx`, client-side extension and size checks (client limit mirrors the server
  default; the server 422/503 remain the real gate with friendly copy), Upload
  disabled while the mutation is pending, inline `role="alert"` errors. **Sources
  table**: filename, status chip, created date. Chip mapping: the four in-flight states
  render a blue "processing" style, `ready` green, `failed` red.
- **Polling**: RTK Query `getSources` with `pollingInterval` = 2s while any row is
  non-terminal, `0` once all rows are terminal (second round: the installed RTK Query
  types type the option `number | undefined` - `false` fails the TypeScript build,
  while `0` disables polling; and `pollingInterval` is RTK Query's option name,
  `refetchInterval` is TanStack Query's) - one endpoint drives the whole status UX,
  no extra status API.
- New `sourcesApi` slice: `getSources` query + `uploadSource` mutation (multipart
  `FormData` through the existing `fetchBaseQuery`), a `Source` cache tag invalidated on
  upload success. Deep-module rule unchanged (S2 spec section 5.3): pages never build
  URLs or parse response bodies.
- Devias styling continuity per S2 spec section 4.

## 8. Testing strategy

TDD throughout; pytest runs against real services from compose (slices spec section 6).
The backend suite now requires db + RabbitMQ + Garage up (documented; no mocking of
storage or broker).
One pre-existing fix lands first, in its own commit (second round):
`backend/alembic/env.py`'s stray `RAG_DATABASE_URL` override (backlog 2026-10-12) -
the S3 migration and the fixtures must not build on that hazard.

1. **Unit**: chunker golden documents; stub parser tests (committed tiny PDF fixture in
   `backend/tests/fixtures/` + an in-test generated docx); stub embedding
   (determinism, dimension, L2 normalization, empty text -> zero vector); object-key
   format; settings defaults; startup dimension guard (matching + mismatching catalog
   fixtures -> refuse with the actionable message) and the `worker_init` handler itself
   -> `SystemExit`, so Celery's Exception-swallowing signal dispatch cannot boot a
   mismatched worker (section 4.3).
2. **API/service (TestClient + savepoint-rollback sessions)**: upload 201 + response
   shape + all rows created (source, item, run `queued`, outbox event with the full
   payload) + Garage object actually written + **no DB transaction open across the
   storage call** (second round: the storage client is patched to capture the
   session's transaction state during the PUT - this pins the commit-vs-rollback trap
   of section 5.1 step 4); validation 422s; editor/viewer 404; public-viewer GET ok /
   upload 404; ingestion service end-to-end (fetch -> parse -> chunk -> one-commit
   persist, run `indexing` + `document_id` linked, chunk `search_vector` matching the
   generated column); duplicate delivery no-ops via claim guard (keyed by run id,
   decision 13); garbage `.pdf` bytes -> `failed` with error text; embed service
   updates vectors in place, conditional `ready` transition, idempotent re-run, batch
   boundaries; sources list derives status + filename from the item's latest run
   (decision 12); project delete with a **fully ingested** source - item + document +
   chunks + run with `document_id` set (second round, so both cascade paths into
   `chunks` and `ingestion_runs` are exercised, and `passive_deletes` is honest) -> 204
   and every cascaded row gone - the regression that motivated the ON DELETE rules.
   `test_alembic` grows: the six new tables exist, FK-index assertions per house style
   (leading columns, section 4.3), and downgrade-to-base drops the `vector` extension.
3. **Outbox/worker integration (real RabbitMQ, `rag_test` vhost)**: a session fixture
   creates the `rag_test` vhost and grants `guest` on it via the 15672 management API
   (both calls idempotent; decision 14) and reads `RAG_TEST_BROKER_URL`, so the
   dispatcher under test runs on an injected `rag_test` app - never the module-level
   dev default. The queues are purged before seeding (a failed run leaves messages
   behind; a later run must not inherit them). Seeded rows -> one dispatcher batch ->
   `published_at` set only after the broker confirm + the message truly on the right
   queue (read with a plain kombu consumer, no Celery worker process); patched-publish
   failure -> `attempts`/`last_error` increment, row retried next tick. The
   multi-process path (API -> broker -> dispatcher -> worker -> DB) is proven by the
   e2e, keeping pytest fast.
4. **Frontend vitest**: upload posts `FormData` (MSW); Upload disabled while pending;
   client-side rejections; server 422/503 friendly copy; table rows + chips; polling
   stops at terminal; project 404 state; list-row navigation.
5. **Playwright e2e** (`npm run e2e`, separate gate): webServer entries = uvicorn
   (8001, `rag_e2e` DB; the entry also runs `e2e_db.py bootstrap`, which creates the
   database *and* the `rag_e2e` vhost, decision 14) + celery worker `--pool=solo` on
   the `rag_e2e` vhost + the dispatcher on the same vhost + Vite (5173 -> 8001). The
   entry array's order is load-bearing (second round): the installed Playwright 1.64
   starts `webServer` entries one at a time, in array order, waiting for each to be
   ready - so the bootstrap entry (which rebuilds `rag_e2e`) necessarily precedes the
   worker and dispatcher entries. The worker and dispatcher expose no ready URL, so
   each logs one ready line (the worker via Celery's `worker_ready` signal) and its
   entry waits on it via `webServer.wait` - on **stderr** (second round), with real
   timeouts: Celery logs to stderr, and its default `worker_redirect_stdouts` sends
   even `print()` output there, so a stdout wait never fires and the entry times out;
   the dispatcher logs its ready line to stderr too, since piped Python stdout is
   block-buffered and an unflushed `print` may never arrive. The worker's ready line
   must be visible at its default WARNING log level (or the entry passes
   `--loglevel=INFO`).
   Journey: register -> open the Default project -> upload the committed tiny PDF
   fixture (shared from `backend/tests/fixtures/`) + a runtime-generated .docx (small
   script using python-docx) -> both chips reach `Ready` with an explicit assertion
   timeout inside the 30s test budget (the default 5s expect timeout does not cover
   the full pipeline). Stale queue messages after DB truncation are absorbed by the
   ack-and-skip guards; already-uploaded Garage objects are orphaned harmlessly (no
   delete path in S3). Bootstrap and truncate scripts grow the six new tables.

Gates (house rules): backend `ruff check .`, `ruff format --check .`, `mypy app tests`,
`pytest`; web `npm run lint`, `format:check`, `test`, `build`; `npm run e2e` stays a
separate gate, never in the default run.

## 9. Docs and runbook updates

- README backend runbook: compose services (Garage with its fixed dev credentials,
  including the warning that changing `GARAGE_DEFAULT_SECRET_KEY` after first start
  bricks the volume until the Garage metadata volume is wiped - section 3.2), the
  three dev commands (section 3.5), test prerequisites (db + RabbitMQ + Garage, and
  the test vhost). The pre-existing "README lacks web instructions" backlog item
  remains a separate docs task; S3 adds only what it introduces.
- Slices-spec sync (second round): the S3 roadmap row and the preview section flipped
  to Garage with the first review round (`8f6ad96`), so this slice touches no other
  `2026-10-06-rag-mvp-slices-design.md` text. The slices spec's one remaining MinIO
  mention (its section 7 next-step line) flips with the slice-completion status update
  below, and its S7 row keeps "Celery Beat sync polling" as an open option, because
  decision 3 no longer decides S7's scheduler (S7's round picks between extending the
  dispatcher loop and a standalone `celery beat` process).
- At slice completion this spec's status and the slices spec's S3 row flip to
  implemented (as S2 did).

## 10. Risks and accepted costs

| Risk | Stance |
|---|---|
| Celery on Windows (prefork unsupported) | `--pool=solo` in dev/e2e, documented |
| Garage provisioning | `garage server --single-node --default-bucket` with compose-fixed credentials; nothing to order, re-run, or write out |
| Dispatcher is a third local process | documented runbook + e2e entries; the loop is one screenful and restarts stateless |
| Worker crash mid-run leaves the run (and the derived source status) non-terminal | accepted S3 cost: dev restarts the worker and re-uploads; recovery (stale-run sweep) is S7, backlog-tracked |
| Stub PDF parser yields no headings | honest: PDFs get page-paragraphs and empty `heading_path`; DOCX gives real paths; real structure arrives with Unstructured (S5) |
| Stub embeddings = lexical-ish similarity | intentional: makes S4 retrievable offline; provider swap is S5 |
| Whole file bytes in memory (sync stack) | fine at the 25MB cap, documented |
| Backend suite now needs RabbitMQ + Garage | documented; real services, no mocks |

## 11. Out of scope (S3 bounds)

Retrieval + query UI (S4); real providers + rerank + API keys (S5); `/answer` (S6); sync
polling (`sync_interval`/`last_sync_at`), idempotency hardening, stale document
replacement/deletion and activation semantics, stuck-run recovery, retries/backoff,
poison-event caps, source delete, ingestion-run status surfacing in the UI (S7); the
API-side dimension guard (S4); website connector + multi-item sources (`url`,
`remote_version`, `last_seen_at`, `deleted_at`, `sources.config`) (S9); table, code, and
image_caption chunk types; pagination; batch/multi-file upload; queue purging (as a
product feature - the pytest fixture's pre-seed purge in section 8 is test hygiene);
Celery
result backends; auth changes.

## 12. Done when

A real PDF uploads from the browser (dev runbook flow) and its source row travels
`queued` -> `ready` fully offline: the backend suite passes against compose db +
RabbitMQ + Garage (unit, API/service, outbox integration on the `rag_test` vhost), the
web suites pass (vitest, lint, build), the Playwright full-pipeline journey proves
upload -> `ready` through the real worker + dispatcher, and both spec statuses are
updated.
