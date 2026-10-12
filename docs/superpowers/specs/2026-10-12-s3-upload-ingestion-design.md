# S3 - Upload & Ingestion (stub providers) + Upload UI - Design

Date: 2026-10-12
Status: Approved design; ready for the implementation plan.
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

## 2. Decisions (from the 2026-10-12 design round)

1. **Garage replaces MinIO now.** Chosen from the backlog's candidates (Garage vs
   SeaweedFS) for a single-container footprint, minimal config, and active maintenance.
   The `minio` service, `miniodata` volume, and the EOL TODO comment are removed
   (dev-only data). Bootstrap in section 3.2.
2. **All pipeline triggers go through the transactional outbox.** The upload transaction
   writes a `source_item_ingestion_requested` event; the API process never touches
   RabbitMQ. No commit-then-publish gap, no lost task on a crash between commit and
   publish, and one mechanism carries both pipeline triggers (MD section 18).
3. **The outbox dispatcher runs on Celery Beat from S3** (pulled forward from S7 at the
   design round): a `dispatch_outbox` Beat task every `outbox_poll_interval_seconds`
   (default 1s), routed to the `ingestion` queue. Dev/e2e run worker + embedded Beat
   (`-B`) as one process; a multi-worker deployment splits Beat out with no code change.
   S7 later adds sync schedules to the same Beat config with zero new infrastructure.
4. **The stub embedding is a deterministic hash-bag**: lowercase word split, each token
   sha256-hashed into one of `embedding_dim` buckets with a sign bit, L2-normalized. Same
   text always yields the same vector - idempotent re-runs and reproducible tests - and
   cosine similarity behaves like soft lexical overlap so S4 retrieval is meaningful
   fully offline. Empty text yields the zero vector (documented).
5. **Token counting for chunking is a documented estimate** (words x 4/3); no tokenizer
   dependency. Settings stay in token units (MD section 9): target 600, max 1000,
   overlap 80.
6. **Full-pipeline Playwright e2e**: the journey runs against the real worker (solo pool
   + embedded Beat) and asserts upload -> `ready` through the browser, covering both
   stub parsers via the true broker path. Chosen over split coverage at the design round.
7. **Deferred decisions finalized** (slices spec section 5 table): #3
   `documents.normalized_content` JSONB holds the elements array; #4 settings-driven
   `embedding_dim` (stub: 384) with the migration + re-embedding comment (section 3.3);
   #7 object key `raw/{project_id}/{source_item_id}/{content_hash}/{filename}`; #9
   replace-only-after-success - decided now, with the deletion logic itself shipping in
   S7 (no replacement path exists in S3: each upload creates a new source).
8. **`ingestion_runs` keys on `source_item_id` only** (design-round amendment; the MD
   section 27 draft had `source_id`, which is one join away through `source_items`).
9. **Startup dimension guard**: API and worker compare `embedding_dim` against the actual
   `chunks.embedding` catalog type at boot and refuse to start on mismatch with an
   actionable message (section 4.3).
10. **The re-embedding follow-up is recorded in the backlog** (2026-10-12): swapping the
    embedding model or dimension invalidates stored vectors; re-embedding runs from
    persisted `chunks.text` (no re-parse), clearing embeddings and re-enqueueing one
    outbox event per document.

## 3. Dependencies and infrastructure

### 3.1 Backend dependencies (`backend/pyproject.toml`)

| Package | Use |
|---|---|
| `celery>=5.5` | worker + Beat (RabbitMQ broker; kombu/amqp ship with it) |
| `boto3` | Garage/S3 client (path-style addressing) |
| `pypdf` | stub PDF parser |
| `python-docx` | stub DOCX parser |

No Celery result backend: task outcomes live in Postgres (`ingestion_runs`); Celery moves
messages only.

### 3.2 Compose: Garage replaces MinIO (`deploy/docker-compose.yml`)

- Service `garage`: `dxflrs/garage` (version pinned at implementation), config mounted
  from `deploy/garage.toml` (replication_factor 1, S3 API on `0.0.0.0:3900`, admin API on
  3903), named volumes for meta and data. Ports 3900 + 3903.
- The `minio` service, its `miniodata` volume, and the EOL TODO comment are removed.
  `docker compose up` now yields db + RabbitMQ + Garage.
- **Bootstrap (idempotent, run once per environment)**: a small script wrapping
  `docker compose exec garage garage ...` commands that assigns the single-node layout
  (zone `dc1`, capacity 1G), applies it, creates the `rag-dev` bucket, creates the
  `rag-dev` access key via `garage key new --name rag-dev`, and writes the printed
  credentials to a git-ignored `backend/.env` (pydantic-settings already reads it). The
  script fails with a clear message if Garage is not ready. Exact command syntax is pinned
  during implementation.

### 3.3 Settings additions (`app/core/config.py`, `RAG_` prefix)

| Setting | Default | Use |
|---|---|---|
| `broker_url` | `amqp://guest:guest@localhost:5672//` | Celery broker |
| `s3_endpoint` | `http://localhost:3900` | Garage S3 API |
| `s3_access_key` / `s3_secret_key` | empty (bootstrap writes them) | credentials |
| `s3_region` / `s3_bucket` | `us-east-1` / `rag-dev` | client config |
| `embedding_dim` | 384 | stub vector size; migration column type |
| `parser_provider` / `embedding_provider` | `stub` / `stub` | provider selection |
| `chunk_target_tokens` / `chunk_max_tokens` / `chunk_overlap_tokens` | 600 / 1000 / 80 | chunker budgets |
| `embedding_batch_size` | 64 | embed batching |
| `outbox_poll_interval_seconds` / `outbox_batch_size` | 1.0 / 20 | Beat schedule / dispatch batch |
| `max_upload_mb` | 25 | upload validation |

`embedding_dim` carries an inline comment: changing it requires an Alembic migration
(the `chunks.embedding` column is typed from this setting at migration time) **and**
re-embedding every stored chunk (backlog 2026-10-12; re-embedding runs from
`chunks.text`, no re-parse needed).

### 3.4 Module layout (slices spec section 3 map)

```
backend/app/
  core/         + outbox ORM model (models.py); session_scope helper (db.py)
  sources/      models.py, router.py, schemas.py, service.py    # upload + list
  ingestion/    models.py (documents, chunks, ingestion_runs), service.py, chunking.py
  storage/      service.py                                       # boto3 put/get
  providers/    base.py (Parser, EmbeddingProvider, NormalizedDocument),
                stub_parser.py, stub_embeddings.py
  workers/      celery_app.py, tasks.py, outbox.py              # app, thin tasks, dispatch
```

Queue names `ingestion` / `embed` are constants in `app/workers/celery_app.py`. Celery
tasks are thin wrappers over `app/ingestion/service.py` functions (keyword-only session
arguments), so pipeline logic tests without Celery. Workers get sessions through a
`session_scope` context manager in `app/core/db.py` (request-scoped `get_db` does not
apply outside HTTP). `alembic/env.py` imports the new model modules for autogenerate.

### 3.5 Runbook (dev + e2e)

```
docker compose up -d                    # db + rabbitmq + garage (deploy/)
uvicorn app.main:app                    # API
celery -A app.workers.celery_app worker --pool=solo -B -Q ingestion,embed
```

Prefork is unsupported on Windows; `--pool=solo` is the supported dev pool. Embedded Beat
(`-B`) keeps worker + scheduler as one process for the single-worker MVP.

## 4. Data model

### 4.1 Tables (one Alembic migration; house style: UUID pk, `func.now()` timestamps)

```
sources          id, project_id -> projects, type (check 'upload'), config JSONB
                 (filename, content_type, size_bytes), status (check 4.2),
                 sync_interval (nullable int seconds; unused until S7), last_sync_at
                 (nullable; sync arrives S7), created_at
source_items     id, source_id -> sources, external_id (= sha256 of raw bytes),
                 url (nullable), remote_version (nullable), content_hash,
                 last_seen_at (set at creation; sync updates it from S7),
                 deleted_at (nullable)
documents        id, source_item_id -> source_items, content_hash (sha256 of canonical
                 normalized JSON), raw_object_key, normalized_content JSONB (the full
                 normalized document: title, elements, metadata), created_at
chunks           id, project_id -> projects (intentional denormalization for the
                 retrieval hot path - rationale comment in the model, MD section 27),
                 document_id -> documents, position, text, heading_path JSONB (string
                 array), chunk_type (check 'text'), metadata JSONB, content_hash
                 (sha256 of text), embedding vector(embedding_dim) NULL until embedded,
                 search_vector tsvector NOT NULL, unique(document_id, position)
ingestion_runs   id, source_item_id -> source_items, document_id (nullable), status,
                 attempt (default 1), started_at, finished_at, error
outbox_events    id, event_type, aggregate_type, aggregate_id (uuid), payload JSONB,
                 created_at, published_at (nullable), attempts (default 0), last_error;
                 partial index on created_at WHERE published_at IS NULL
```

- `ingestion_runs` keys on `source_item_id` only (decision 8); `sources.status` mirrors
  the latest run's status.
- Chunk `metadata` for S3 carries `{"filename": ...}` from the source config - the
  citation-ready minimum S4's retrieval response will surface.
- Hashes: raw-bytes sha256 -> `source_items.content_hash` + `external_id`; canonical
  normalized JSON (sorted keys) sha256 -> `documents.content_hash`; chunk-text sha256 ->
  `chunks.content_hash`.
- `search_vector` is set at chunk insert via `to_tsvector('english', text)` - the formula
  lives in one place and S4 stays free to change weighting.

### 4.2 Status machine (MD section 6)

`queued | fetching | processing | indexing | ready | failed`, as check constraints on
`sources.status` and `ingestion_runs.status`.

| Status | Set by |
|---|---|
| `queued` | upload endpoint (rows created) |
| `fetching` | ingestion task claim |
| `processing` | ingestion task, after raw bytes are fetched |
| `indexing` | the document+chunks+outbox commit |
| `ready` | embed task, after vectors are updated |
| `failed` | either task on error (error text on the run; no auto-retries in S3 - S7) |

### 4.3 pgvector + indexes in the migration

- `CREATE EXTENSION IF NOT EXISTS vector`.
- `chunks.embedding vector(N)` where N = `embedding_dim` read from settings at migration
  time; changing it requires a new migration (decision #4; comment on the setting).
- HNSW: `USING hnsw (embedding vector_cosine_ops)`; GIN: `USING gin (search_vector)` -
  both created with this slice's schema so S4's retrieval queries rely on them.
- **Startup guard**: API and worker compare the column's catalog type (`format_type`
  over `pg_attribute`, parse the dimension) with `embedding_dim` and fail fast, e.g.
  "chunks.embedding is vector(384) but RAG_EMBEDDING_DIM is 512; changing the dimension
  requires an Alembic migration". This prevents a cryptic psycopg insert failure deep in
  the embed path after chunks are already committed.

## 5. Ingestion pipeline

### 5.1 Upload flow (`POST /projects/{project_id}/sources`)

1. Authorization: `get_project_for_user_with_role(minimum_role="editor")`; None -> 404
   "project not found" (house convention: 404 hides both missing and forbidden).
   Viewer-role and public-project users cannot upload.
2. Validation: filename extension `.pdf`/`.docx`, non-empty, size <= `max_upload_mb`;
   violations -> 422 with a friendly detail.
3. sha256 the bytes; build the key
   `raw/{project_id}/{source_item_id}/{content_hash}/{filename}` (decision #7).
4. PUT the object to Garage - raw persisted before parsing (MD section 30). Storage
   failure -> 503 with a retryable message, no rows written.
5. One transaction: `sources` (type `upload`, status `queued`) + `source_items` +
   `ingestion_runs` (`queued`, attempt 1) + `outbox_events` row
   `source_item_ingestion_requested` (aggregate source_item; payload
   `{"source_item_id": ...}`) -> commit -> 201 `SourceRead`.

### 5.2 Outbox dispatcher (Celery Beat task `dispatch_outbox`)

- Beat schedules it every `outbox_poll_interval_seconds`; the task is routed to the
  `ingestion` queue so the single worker consumes everything (MD section 17).
- Task body: select unpublished rows (batch `outbox_batch_size`, ordered `created_at`,
  `FOR UPDATE SKIP LOCKED`); publish each via `celery_app.send_task` to the queue mapped
  from `event_type`; set `published_at` on success; on failure `attempts += 1` + record
  `last_error`, retried next tick.
- Duplicate publishes are expected (crash between publish and mark, MD section 18);
  consumers are idempotent. Poison events retry indefinitely in S3; backoff/caps are S7
  robustness scope.
- Routing: `source_item_ingestion_requested` -> `ingestion`;
  `document_ready_for_embedding` -> `embed`.

### 5.3 Ingestion task (`ingest_source_item`, queue `ingestion`)

- **Claim guard**: `UPDATE ingestion_runs SET status='fetching', started_at=now() WHERE
  source_item_id = :id AND status='queued'`; zero rows updated -> duplicate delivery or
  stale message -> ack, no-op. Missing subject rows -> ack, skip (absorbs stale queue
  messages, e.g. after e2e DB truncation).
- fetching: pull raw bytes from Garage through the storage module.
- processing: parser provider -> `NormalizedDocument` (title from filename; elements
  `{type, level?, text}`); document `content_hash` from the canonical JSON. A document
  with zero extractable elements (e.g. a scanned PDF) raises a parse error -> run
  `failed` with a clear message.
- chunk: the structure-aware chunker (section 5.5).
- One transaction (MD section 30): document row + all chunks (`search_vector` computed,
  `embedding` NULL) + `document_ready_for_embedding` outbox row + run `indexing` ->
  commit. No transaction spans storage or provider calls.
- Any failure -> run + source `failed` with the error text. `sources.status` mirrors
  every run transition.

### 5.4 Embed task (`embed_document`, queue `embed`)

- Load document + chunks; batch them (`embedding_batch_size`) through
  `embed_documents`; UPDATE `chunks.embedding` in place - in-place updates make
  duplicate delivery naturally idempotent (deterministic stub: same text -> same vector).
- Then run + source -> `ready` (`finished_at` set) via a conditional
  `WHERE status='indexing'` transition. Missing document -> ack, skip. Errors ->
  `failed`.

### 5.5 Chunker (`app/ingestion/chunking.py`, replaceable by design)

Structure-aware recursive chunking (MD section 9):

- Walk elements keeping a heading stack; each chunk records its `heading_path`.
- Pack consecutive paragraphs under the same heading until estimated tokens
  (words x 4/3) exceed `chunk_target_tokens`; a single element over
  `chunk_max_tokens` hard-splits by words with `chunk_overlap_tokens` overlap.
- Golden-document unit tests cover: heading boundaries, target packing, max enforcement
  with overlap, `heading_path` correctness, tiny document -> one chunk, and an empty
  element list -> the chunker raises (empty extraction is a parse failure per section
  5.3, so the chunker never silently produces zero chunks).

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
| `POST /projects/{project_id}/sources` | `get_current_user` + editor role | section 5.1; 201 `SourceRead`; 422 validation; 503 storage; 404 house convention |
| `GET /projects/{project_id}/sources` | `get_current_user` + `get_project_visible_to_user` | list newest-first; no pagination in S3 |

`SourceRead = {id, project_id, type, status, filename, created_at}` (filename surfaced
from `sources.config`). Errors use FastAPI's `{detail}` shape like the rest of the API.
Routers handle HTTP only; row creation + listing live in `app/sources/service.py`.

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
- **Polling**: RTK Query `getSources` with `refetchInterval` = 2s while any row is
  non-terminal, `false` once all rows are terminal - one endpoint drives the whole
  status UX, no extra status API.
- New `sourcesApi` slice: `getSources` query + `uploadSource` mutation (multipart
  `FormData` through the existing `fetchBaseQuery`), a `Source` cache tag invalidated on
  upload success. Deep-module rule unchanged (S2 spec section 5.3): pages never build
  URLs or parse response bodies.
- Devias styling continuity per S2 spec section 4.

## 8. Testing strategy

TDD throughout; pytest runs against real services from compose (slices spec section 6).
The backend suite now requires db + RabbitMQ + Garage up (documented; no mocking of
storage or broker).

1. **Unit**: chunker golden documents; stub parser tests (committed tiny PDF fixture in
   `backend/tests/fixtures/` + an in-test generated docx); stub embedding
   (determinism, dimension, L2 normalization, empty text -> zero vector); object-key
   format; settings defaults; startup dimension guard.
2. **API/service (TestClient + rollback sessions)**: upload 201 + response shape + all
   rows created (source, item, run `queued`, outbox event) + Garage object actually
   written; validation 422s; editor/viewer 404; public-viewer GET ok / upload 404;
   ingestion service end-to-end (fetch -> parse -> chunk -> one-commit persist, run
   `indexing`, chunk `search_vector` set); duplicate delivery no-ops via claim guard;
   garbage `.pdf` bytes -> `failed` with error text; embed service updates vectors in
   place, conditional `ready` transition, idempotent re-run, batch boundaries.
3. **Outbox/worker integration (real RabbitMQ)**: seeded outbox rows ->
   `dispatch_outbox` -> `published_at` set + the message truly on the right queue
   (drained with a plain kombu consumer, no Celery worker process); patched-send
   failure -> `attempts`/`last_error` increment, row retried. The multi-process path
   (API -> broker -> worker -> DB) is proven by the e2e, keeping pytest fast.
4. **Frontend vitest**: upload posts `FormData` (MSW); Upload disabled while pending;
   client-side rejections; server 422/503 friendly copy; table rows + chips; polling
   stops at terminal; project 404 state; list-row navigation.
5. **Playwright e2e** (`npm run e2e`, separate gate): webServer entries = uvicorn (8001,
   `rag_e2e` DB) + worker `--pool=solo -B` (same env) + Vite (5173 -> 8001); compose
   supplies db + RabbitMQ + Garage. Journey: register -> open the Default project ->
   upload the committed tiny PDF fixture (shared from `backend/tests/fixtures/`) + a
   runtime-generated .docx (small script using python-docx) -> both chips reach `Ready`
   within the 30s budget. Stale queue messages after DB truncation are absorbed by the
   ack-and-skip guards; Garage keeps content-addressed objects (harmless). Bootstrap and
   truncate scripts are extended with the six new tables.

Gates (house rules): backend `ruff check .`, `ruff format --check .`, `mypy app tests`,
`pytest`; web `npm run lint`, `format:check`, `test`, `build`; `npm run e2e` stays a
separate gate, never in the default run.

## 9. Docs and runbook updates

- README backend runbook: compose services + Garage bootstrap, the two dev commands
  (section 3.5), test prerequisites. The pre-existing "README lacks web instructions"
  backlog item remains a separate docs task; S3 adds only what it introduces.
- At slice completion this spec's status and the slices spec's S3 row flip to
  implemented (as S2 did).

## 10. Risks and accepted costs

| Risk | Stance |
|---|---|
| Celery on Windows (prefork unsupported) | `--pool=solo` in dev/e2e, documented |
| Garage bootstrap ordering (layout before writes) | idempotent one-time script; clear failure message if storage is not ready |
| Dispatch ticks delayed behind long tasks (solo pool) | accepted at MVP scale; overlapping dispatch runs are safe (SKIP LOCKED); splitting queues later is config-only |
| Stub PDF parser yields no headings | honest: PDFs get page-paragraphs and empty `heading_path`; DOCX gives real paths; real structure arrives with Unstructured (S5) |
| Stub embeddings = lexical-ish similarity | intentional: makes S4 retrievable offline; provider swap is S5 |
| Whole file bytes in memory (sync stack) | fine at the 25MB cap, documented |
| Backend suite now needs RabbitMQ + Garage | documented; real services, no mocks |

## 11. Out of scope (S3 bounds)

Retrieval + query UI (S4); real providers + rerank + API keys (S5); `/answer` (S6); sync
polling, idempotency hardening (`(source_item_id, content_hash)` uniqueness), stale
document replacement/deletion, retries/backoff, poison-event caps, source delete,
ingestion-run status surfacing in the UI (S7); website connector (S9); table, code, and
image_caption chunk types; pagination; batch/multi-file upload; queue purging; Celery
result backends; auth changes.

## 12. Done when

A real PDF uploads from the browser (dev runbook flow) and its source row travels
`queued` -> `ready` fully offline: the backend suite passes against compose db +
RabbitMQ + Garage (unit, API/service, outbox integration), the web suites pass
(vitest, lint, build), the Playwright full-pipeline journey proves upload -> `ready`
through the real worker, and both spec statuses are updated.
