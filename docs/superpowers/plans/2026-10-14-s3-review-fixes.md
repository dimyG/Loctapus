# S3 Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the pre-merge review of the unmerged `s3-upload-ingestion` branch (three focused review seats - DB schema, service topology, maintainability - 2026-10-13/14) so S4 builds on a coherent base: one upload source per project with filename identity, a database-enforced project scope down to chunks, runs that pin their own file version, an explicit run state machine, a non-starving outbox, transient-failure tolerance in the worker and dispatcher, durable broker state, and a decomposed project page.

**Architecture:** Every schema change amends the unmerged migration `0005` together with its ORM models, and from Task 2 on a model/migration parity test keeps them identical. The ingestion module gains an explicit run state machine (`ingestion/runs.py`) that owns run creation, guarded transitions, and the latest-status expression, so `sources` asks ingestion for work instead of writing its tables. Upload items live in one lazily created upload source per project, keyed by filename; the API becomes `/projects/{project_id}/uploads`. Outbox payloads shrink to ids, the run row carries its file version, and the dispatcher backs failing rows off instead of re-selecting them forever.

**Tech Stack:** unchanged from S3 - FastAPI, SQLAlchemy 2, Alembic, Postgres 17 + pgvector, Celery >= 5.6 on RabbitMQ 3.13, boto3 on Garage v2.3.0, React 19 + RTK Query + MUI, Vitest/MSW, Playwright 1.64.

**Spec:** `../specs/2026-10-12-s3-upload-ingestion-design.md` (Task 14 amends it to match this plan; until then this plan wins where they disagree) plus the S3 plan `2026-10-13-s3-upload-ingestion.md` for context.

## Rulings

User-confirmed (2026-10-14):

- **U1 - One upload source per project.** Each project gets one `upload` source; every uploaded file is a `source_items` row in it, identified by `external_id` = the sanitized filename (exact, case-sensitive match), so `unique(source_id, external_id)` finally bites and a re-upload is recognized as the same item.
- **U2 - Composite FK chain.** `project_id` is repeated on `source_items` and `documents`, and every child references its parent through `(parent_id, project_id) -> parent (id, project_id)`, so the database guarantees `chunks.project_id` equals its source's project. Each composite FK carries a model comment explaining why.
- **U3 - Outbox backoff now.** `outbox_events.next_attempt_at` with capped exponential backoff; the attempts cap and dead-lettering stay in S7.

Executor rulings (made while planning; each with its cost if wrong):

- **R1 - Amend `0005` in place, no `0006`.** Verified 2026-10-13: the dev database is at `0004`, `rag_e2e` is dropped and recreated by every bootstrap, and `rag_test` is dropped at session end. Cost if wrong: an environment that already ran the old `0005` must drop its S3 tables (or the database) before upgrading.
- **R2 - Same-name policy in S3.** A new filename creates a new item. A filename whose item's latest run is `failed` and that has no `documents` row becomes a new version of the same item (the retry path; nothing indexed exists to replace). Every other same-name upload is a `409`. Replacing indexed content stays S7 (replace-only-after-success). Cost if wrong: S7 relaxes the 409 into replacement, which is additive.
- **R3 - The API lists uploads, not sources.** `POST/GET /projects/{project_id}/uploads` return `UploadOut` (`id` = source item id); the `/sources` routes and `SourceOut` are removed, because with U1 a project has one source and the rows users see are its items. S9 adds a sources listing when website sources make sources user-visible. Cost if wrong: a route rename in one router, one API slice, and their tests.
- **R4 - Thin ingestion payload.** `source_item_ingestion_requested` carries `{"ingestion_run_id"}` only; the run row stores `raw_object_key` + `content_hash` (the version it was created for), the worker verifies the fetched bytes' sha256 against it, and the document records the run's key. This keeps decision 13's guarantee (an older run never processes newer bytes) but moves the truth from the message into the database, so S7's stale-run sweep can re-drive a run from its row. Cost if wrong: none functionally; one extra row read per task.
- **R5 - Lazy upload source.** Created on the first upload by `INSERT ... ON CONFLICT DO NOTHING` against a partial unique index, then selected; `projects` stays unaware of sources and no backfill is needed. Cost if wrong: none; eager creation could be added later without schema change.
- **R6 - Content type from the extension.** The stored and Garage content type comes from `SUPPORTED_UPLOAD_TYPES`, never from the client header. Cost if wrong: none.
- **R7 - Transient database errors retry.** `pool_pre_ping=True` everywhere plus task autoretry on SQLAlchemy `OperationalError`/`InterfaceError` (backoff capped at 60s, 5 retries); the claim guard makes a retried ingestion safe and embed is idempotent. A database loss after the claim still strands the run (S7 sweep). Cost if wrong: duplicated work on retry, which both legs absorb.
- **R8 - One model registry for entry points.** `app/models.py` imports every model module and configures mappers; only entry points import it (`app.main`, `app.workers.celery_app`, `alembic/env.py`). It replaces the declaration-site imports from `66ca851`, which cannot cover both directions (importing `app.identity.models` alone still fails to configure). Cost if wrong: a new entry point that forgets the import fails at its first flush - the architecture test in Task 1 covers the known ones.
- **R9 - User-safe run errors.** `ingestion_runs.error` stores fixed copy (table below); full exception detail goes only to the worker log. Cost if wrong: S7's UI shows less detail than the log, which is the intent.

## Global Constraints

- Work on branch `s3-upload-ingestion` in `.worktrees/s3-upload-ingestion` (unmerged; these are pre-merge fixes). One concern per commit; each task's commits are listed in its steps.
- Gates, from `backend/` (venv at the repo root: `..\.venv\Scripts\...`): `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest`. From `web/`: `npm run lint`, `npm run format:check`, `npm run test`, `npm run build`. `npm run e2e` is a separate gate, run in Task 13. Every commit leaves its side's gates green.
- Compose services up for pytest and e2e: `docker compose -f deploy/docker-compose.yml up -d`.
- Schema rule: every schema change edits `backend/alembic/versions/0005_ingestion_outbox.py` (upgrade and downgrade, symmetric) and the ORM in the same commit; `test_models_match_migrations` (Task 2) and `test_migrations_downgrade_to_base` stay green. After editing `0005`, drop any leftover test database before the next run, because conftest only creates a missing database and `upgrade head` would no-op on a stale one: `docker exec rag-db-1 psql -U rag -d postgres -c "DROP DATABASE IF EXISTS rag_test"` (or the worktree's own `RAG_TEST_DATABASE_URL` name).
- Python style: keyword-only parameters, line length 110, docstrings on every module/class/function followed by a blank line, comments capitalized and ending with a dot, never the em dash. Frontend: TypeScript strict, no `any`, ESLint `--max-warnings 0`, Prettier width 100, pages never build URLs or parse response bodies.
- Module dependency rule: `sources` may call `ingestion.runs`, `ingestion.status`, and `storage`; `ingestion` may read `sources.models`; only `sources.router` imports `sources.service`; feature modules never import `app.models`.
- The pytest harness runs each test inside one outer transaction, so `now()` is identical for every row a test writes: tests about ordering or backoff set timestamps explicitly or compare against that shared `now()`.
- Unchanged S3 values (S3 plan, Global Constraints) still hold: `STUB_EMBEDDING_DIM = 384`, chunk budgets 600/1000/80, `embedding_batch_size` 64, `outbox_poll_interval_seconds` 1.0, `outbox_batch_size` 20, `max_upload_mb` 25, object key `raw/{project_id}/{source_item_id}/{content_hash}/{filename}`, queue names `ingestion`/`embed`, task names `ingest_source_item`/`embed_document`, vhosts `/`, `rag_test`, `rag_e2e`.
- New settings (exact defaults): `outbox_retry_base_seconds: float = 1.0`, `outbox_retry_max_seconds: float = 300.0`, `outbox_publish_timeout_seconds: float = 10.0`; `parser_provider: Literal["stub"]`, `embedding_provider: Literal["stub"]`.
- User-facing copy (exact):

| Where | Copy |
|---|---|
| 409 duplicate upload | `A file with this name already exists in this project.` |
| 422 unknown size | `The file size could not be determined.` |
| Client empty-file check | `The file is empty.` (mirrors the server) |
| Run error: fingerprint mismatch | `The stored file does not match the upload. Upload the file again to retry.` |
| Run error: object missing | `The stored file is missing. Upload the file again to retry.` |
| Run error: storage unavailable | `File storage was unavailable. Upload the file again to retry.` |
| Run error: zero chunks, and parser "no elements" | `No text could be extracted from this file.` |
| Parser: unreadable PDF / DOCX | `This PDF file could not be read.` / `This DOCX file could not be read.` |
| Parser: unsupported suffix | `This file type is not supported.` |
| Run error: anything else | `Processing failed unexpectedly.` |

## Review Focus

Failure modes most likely to bite a person using this software; each is pinned by a test in the owning task.

1. **The same file uploaded again while the first copy is still processing** - must be a 409 with one item and one run, never a second racing run: Task 8 `test_duplicate_filename_in_flight_is_rejected`.
2. **Re-upload after a failure while an older message for that item can still arrive** - the new run processes the new bytes and an older run only ever its own version: Task 5 `test_older_run_uses_its_own_version`, Task 8 `test_failed_file_can_be_uploaded_again`.
3. **Postgres restarts under a running worker and dispatcher** - pooled connections are re-pinged, tasks retry, and the dispatch loop keeps ticking: Task 10 `test_engine_pings_connections_before_use` and `test_tasks_retry_transient_database_errors`, Task 9 `test_loop_survives_a_failing_tick`.
4. **A writer bug assigns a row to another project** - the database rejects it at every level of the chain: Task 3 `test_item_project_must_match_its_source`, `test_document_project_must_match_its_item`, `test_chunk_project_must_match_its_document`.
5. **More poison events than one batch holds** - healthy events behind them still publish: Task 9 `test_unroutable_rows_cannot_starve_the_outbox`.

## Task order

Tasks 2-10 all edit `0005`, the models, or the services they reshape, so they run strictly in order.

| Task | Depends on | May run alongside |
|---|---|---|
| 1 Model registry | - | 11 |
| 2 ORM/migration parity | 1 | 11 |
| 3 Composite project scope | 2 | 11 |
| 4 Run status and runs module | 3 | 11 |
| 5 Runs pin their version | 4 | 11 |
| 6 Storage lifecycle and errors | 5 | 11 |
| 7 Failure reporting and write paths | 6 | 11 |
| 8 Upload source per project, uploads API | 7 | 11 |
| 9 Outbox backoff and dispatcher | 8 | 11, 12 |
| 10 Worker hardening and settings | 9 | 11, 12 |
| 11 Broker durability and chores | - | any (compose and scripts only) |
| 12 Frontend uploads and page split | 8 (the `/uploads` contract) | 9, 10, 11 |
| 13 E2E journey | 10, 11, 12 | - |
| 14 Docs, backlog, final gates | 13 | - |

---

### Task 1: One model registry for entry points

**Files:**
- Create: `backend/app/models.py`
- Modify: `backend/app/ingestion/models.py:24-28`, `backend/app/sources/models.py:12-14`, `backend/app/projects/models.py:21-23` (remove the side-effect imports and their comments)
- Modify: `backend/app/main.py`, `backend/app/workers/celery_app.py`, `backend/alembic/env.py:7-11`
- Test: `backend/tests/test_model_registry.py`

**Interfaces:**
- Produces: importing `app.models` registers every `app/**/models.py` on `Base.metadata` and calls `sqlalchemy.orm.configure_mappers()`. Entry points import it (`import app.models  # noqa: F401`); feature modules never do.

- [ ] **Step 1: Write the failing tests**

```python
ENTRY_POINTS = ("app.main", "app.workers.celery_app", "app.workers.dispatcher")

def test_registry_imports_every_models_module() -> None:
    """Check that app/models.py imports every models module under app/."""
    # Collect app.*.models via pkgutil.walk_packages(app.__path__, "app."), minus "app.models"
    # itself; collect the modules app/models.py imports by parsing it with ast.
    assert found <= imported

@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
def test_entry_point_loads_the_registry(*, entry_point: str) -> None:
    """Check in a fresh interpreter that the entry point pulls in the registry."""
    # subprocess.run([sys.executable, "-c", f"import sys, {entry_point}; "
    #     "assert 'app.models' in sys.modules"], cwd=BACKEND_DIR, check=True)

def test_every_foreign_key_target_resolves() -> None:
    """Check in a fresh interpreter that every FK target table is registered."""
    # Subprocess: import app.models; for every table in Base.metadata, for every fk in
    # table.foreign_keys, touch fk.column (raises NoReferencedTableError when missing).
```

Subprocesses are required: the pytest process has already imported every module through conftest.

- [ ] **Step 2: Run to verify they fail** - `..\.venv\Scripts\python.exe -m pytest tests/test_model_registry.py -v`. Expected: FAIL, `app.models` does not exist.
- [ ] **Step 3: Implement** `app/models.py` (docstring: why it exists and that only entry points import it), remove the three declaration-site imports, and add the registry import to the three entry points (`env.py` replaces its five model imports with the one import).
- [ ] **Step 4: Run the tests and all backend gates.** Expected: green.
- [ ] **Step 5: Commit** - `refactor(backend): register ORM models through one entry-point registry`.

---

### Task 2: ORM/migration parity

**Files:**
- Modify: `backend/app/identity/models.py`, `backend/app/projects/models.py` (the five `0004` indexes), `backend/app/sources/models.py`, `backend/app/ingestion/models.py`, `backend/app/outbox/models.py` (the seven `0005` indexes)
- Test: `backend/tests/test_alembic.py`

**Interfaces:**
- Produces: every migrated index is declared in its model's `__table_args__` under the migration's exact name: `ix_workspaces_owner_user_id`, `ix_teams_workspace_id`, `ix_projects_workspace_id`, `ix_team_memberships_user_id`, `ix_project_team_roles_team_id`, `ix_sources_project_id`, `ix_chunks_project_id`, `ix_ingestion_runs_document_id`, `ix_ingestion_runs_source_item_id_created_at`, `ix_chunks_embedding` (`postgresql_using="hnsw"`, `postgresql_ops={"embedding": "vector_cosine_ops"}`), `ix_chunks_search_vector` (`postgresql_using="gin"`), `ix_outbox_events_created_at_unpublished` (`postgresql_where=text("published_at IS NULL")`).

- [ ] **Step 1: Write the failing test**

```python
def test_models_match_migrations(*, engine: Engine) -> None:
    """Check that autogenerate sees no difference between the ORM models and the migrated schema."""

    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
```

- [ ] **Step 2: Run to verify it fails.** Expected: FAIL with twelve `remove_index` entries.
- [ ] **Step 3: Declare the indexes.** If a difference remains that comes only from alembic's reflection limits (for example a normalized partial-index predicate), exclude exactly that item in the test through a named, commented predicate - never a blanket filter.
- [ ] **Step 4: Run all backend gates.** Expected: green.
- [ ] **Step 5: Commit** - `fix(backend): declare every migrated index on the ORM models`.

---

### Task 3: Composite project scope down to chunks

**Files:**
- Create: `backend/tests/factories.py`, `backend/tests/ingestion/test_project_scope.py`
- Modify: `backend/tests/ingestion/test_service.py` (`_seed_queued_run` moves to the factories), `backend/tests/sources/test_api.py:294-306` (seeds via the factories)
- Modify: `0005`, `backend/app/sources/models.py`, `backend/app/ingestion/models.py`, `backend/app/sources/service.py` (sets `SourceItem.project_id`), `backend/app/ingestion/service.py` (`_load_item_context` reads `SourceItem.project_id` without joining `Source`; `Document.project_id` set from it)

**Interfaces:**
- Produces `tests/factories.py`:
  - `seed_project(*, db: Session, email: str) -> UUID` - registers a user through `app.identity.service.register_user` and returns the default project id.
  - `seed_upload(*, db: Session, project_id: UUID, filename: str = "doc.pdf", content: bytes = b"%PDF-stub") -> SeededUpload`, where `SeededUpload` is a frozen dataclass of `source_id`, `source_item_id`, `ingestion_run_id`, `raw_object_key`, `content_hash`. It writes rows directly (no storage call). Tasks 4, 5, and 8 update its body; its signature stays.
- Produces schema:
  - `sources`: `uq_sources_id_project_id UNIQUE (id, project_id)`.
  - `source_items.project_id uuid NOT NULL`; `fk_source_items_source_id_project_id (source_id, project_id) -> sources (id, project_id) ON DELETE CASCADE` replaces the single `source_id` FK; `uq_source_items_id_project_id UNIQUE (id, project_id)`.
  - `documents.project_id uuid NOT NULL`; `fk_documents_source_item_id_project_id (source_item_id, project_id) -> source_items (id, project_id) ON DELETE CASCADE` replaces the single FK; `uq_documents_id_project_id UNIQUE (id, project_id)`.
  - `chunks`: `fk_chunks_document_id_project_id (document_id, project_id) -> documents (id, project_id) ON DELETE CASCADE` replaces both single FKs (`document_id -> documents`, `project_id -> projects`); `ix_chunks_project_id` stays as the retrieval filter.
- Model comments (required by U2, one per composite FK, worded by the implementer): `project_id` is repeated down sources -> source_items -> documents -> chunks so retrieval filters chunks by project without joins; the composite FK makes the database reject any row whose project differs from its parent's, so the tenant boundary is enforced by Postgres rather than remembered by writers; the parent's `UNIQUE (id, project_id)` exists only because a composite FK needs a unique target.

- [ ] **Step 1: Move the seeds onto the factories** (behavior-preserving), run the backend gates, commit - `test(backend): share row factories across the S3 test modules`.
- [ ] **Step 2: Write the failing scope tests** in `test_project_scope.py`, each seeding two projects with `seed_project` and expecting `sqlalchemy.exc.IntegrityError` on flush:
  - `test_item_project_must_match_its_source` - a `SourceItem` whose `source_id` belongs to project A with `project_id` = B.
  - `test_document_project_must_match_its_item` - the same for a `Document`.
  - `test_chunk_project_must_match_its_document` - the same for a `Chunk`.
  
  Also extend `test_ingest_end_to_end` to assert every chunk's `project_id` equals its document's, item's, and source's `project_id`.
- [ ] **Step 3: Run to verify they fail.** Expected: the three scope tests FAIL (no composite FKs yet).
- [ ] **Step 4: Implement** the schema, the comments, and the writers (the factories set `project_id` on items and documents too).
- [ ] **Step 5: Run all backend gates.** `test_project_delete_cascades_fully_ingested_source`, `test_foreign_key_columns_are_indexed` (composite FKs lead with columns already covered by the composite uniques), and `test_migrations_downgrade_to_base` must stay green.
- [ ] **Step 6: Commit** - `feat(backend): enforce the project scope down to chunks with composite foreign keys`.

---

### Task 4: Run status vocabulary and the runs module

**Files:**
- Create: `backend/app/ingestion/status.py`, `backend/app/ingestion/runs.py`, `backend/app/ingestion/schema_guard.py`
- Modify: `0005`, `backend/app/ingestion/models.py`, `backend/app/ingestion/service.py`, `backend/app/sources/service.py`, `backend/app/sources/schemas.py`, `backend/app/workers/celery_app.py` (guard import path), `backend/tests/factories.py`
- Test: create `backend/tests/ingestion/test_runs.py`; move the guard tests from `tests/ingestion/test_service.py` into a new `tests/ingestion/test_schema_guard.py`; update `tests/sources/test_api.py`

**Interfaces:**
- `app.ingestion.status`: `class RunStatus(StrEnum)` with `QUEUED`, `FETCHING`, `PROCESSING`, `INDEXING`, `READY`, `FAILED` (values as today); `TERMINAL_RUN_STATUSES: frozenset[RunStatus]` = ready, failed.
- `app.ingestion.runs` - no function commits; callers own the transaction:
  - `request_ingestion(*, db: Session, source_item_id: UUID, raw_object_key: str, content_hash: str) -> UUID` adds the queued run and its outbox event and returns the run id.
  - `claim_run(*, db: Session, run_id: UUID) -> bool` - queued to fetching, sets `started_at`.
  - `start_processing(*, db: Session, run_id: UUID) -> bool` - fetching to processing.
  - `mark_indexing(*, db: Session, run_id: UUID, document_id: UUID) -> bool` - processing to indexing.
  - `mark_ready(*, db: Session, run_id: UUID, expected: RunStatus, document_id: UUID | None = None) -> bool` - indexing or processing to ready, sets `finished_at`.
  - `mark_failed(*, db: Session, run_id: UUID, expected: RunStatus, error: str) -> bool` - fetching, processing, or indexing to failed, sets `finished_at`.
  - `latest_run_status(*, source_item_id: ColumnElement[UUID]) -> ScalarSelect[str]` - correlated subquery, `ORDER BY created_at DESC, id DESC LIMIT 1`.
  - The allowed (from, to) pairs live in one private frozenset; any other pair raises `ValueError` before any SQL runs.
- `app.ingestion.schema_guard`: `query_embedding_dimension`, `verify_embedding_dimension`, `run_startup_checks`, moved unchanged except that the catalog query matches `a.attrelid = to_regclass('chunks')` instead of `c.relname = 'chunks'` (backlog `3587104`).
- Schema (`0005` + ORM): the model builds the status check from `RunStatus` (the migration keeps its literal); new check `(status IN ('ready', 'failed')) = (finished_at IS NOT NULL)`; new check `size_bytes > 0` on `source_items`; `ix_ingestion_runs_source_item_id_created_at` becomes `ix_ingestion_runs_source_item_id_created_at_id` on `(source_item_id, created_at, id)` so the latest-run lookup is a pure index scan.
- `SourceOut.status: RunStatus` (an enum in OpenAPI; Task 8 carries it into `UploadOut`).

- [ ] **Step 1: Write the failing tests** in `test_runs.py`:

```python
def test_status_enum_matches_the_migrated_check(*, engine: Engine) -> None:
    # pg_get_constraintdef of the ingestion_runs status check; its quoted literals
    # == {status.value for status in RunStatus}.

def test_disallowed_transition_raises_without_touching_the_row(*, db_session: Session) -> None:
    # mark_failed(expected=RunStatus.QUEUED, ...) raises ValueError; the run is still queued.

def test_transitions_follow_the_pipeline(*, db_session: Session) -> None:
    # claim_run, start_processing, mark_indexing, mark_ready(expected=INDEXING) each return
    # True in order; a second claim_run returns False.

def test_finished_at_must_match_a_terminal_status(*, db_session: Session) -> None:
    # A run with status ready and finished_at None raises IntegrityError on flush.

def test_latest_run_status_prefers_the_newest_run(*, db_session: Session) -> None:
    # Runs at T (failed) and T + 1s (queued), created_at set explicitly -> "queued".

def test_latest_run_status_breaks_ties_by_id(*, db_session: Session) -> None:
    # Two runs with the same created_at, ids UUID(int=1) (failed) and UUID(int=2) (ready)
    # -> "ready", and the sources list returns exactly one row for that source.

def test_request_ingestion_adds_a_queued_run_and_its_event(*, db_session: Session) -> None:
```

- [ ] **Step 2: Run to verify they fail.** Expected: import errors (`app.ingestion.status`/`runs` missing), and the tie test returns two rows on today's query.
- [ ] **Step 3: Status vocabulary** - add `status.py`, build the model check from it, add the two new checks to `0005` and the models, type `SourceOut.status`. Gates green. Commit: `refactor(backend): name the run statuses and add run-state check constraints`.
- [ ] **Step 4: Runs module** - add `runs.py`; `ingestion/service.py` calls its transitions (and keeps its commits), and `sources/service.py` calls `request_ingestion` instead of building `IngestionRun` and the event itself; update `seed_upload`. Gates green. Commit: `refactor(backend): move run transitions and ingestion requests into ingestion.runs`.
- [ ] **Step 5: Latest-run fix** - the sources list uses `func.coalesce(latest_run_status(...), RunStatus.QUEUED)` and orders by `created_at DESC, id DESC`; change the index in `0005` and the model. Gates green. Commit: `fix(backend): derive the latest run with an id tie-break and an index-backed lookup`.
- [ ] **Step 6: Guard split** - move the guard into `schema_guard.py` with the `to_regclass` fix and move its tests. Gates green. Commit: `refactor(backend): split the embedding dimension guard into its own module`.

---

### Task 5: Runs pin their file version; typed event contract

**Files:**
- Modify: `0005`, `backend/app/ingestion/models.py`, `backend/app/ingestion/runs.py`, `backend/app/ingestion/service.py`, `backend/app/outbox/events.py`, `backend/app/workers/tasks.py`, `backend/app/workers/dispatcher.py`, `backend/tests/factories.py`
- Test: `backend/tests/outbox/test_events.py`, `backend/tests/ingestion/test_service.py`, `backend/tests/workers/test_dispatcher_integration.py`; create `backend/tests/workers/test_task_contract.py`

**Interfaces:**
- Schema: `ingestion_runs.raw_object_key varchar NOT NULL` and `ingestion_runs.content_hash varchar NOT NULL` - the file version the run was created for.
- `request_ingestion` stores both on the run; the event payload is `{"ingestion_run_id": str}`.
- `app.outbox.events`:
  - `INGEST_SOURCE_ITEM_TASK = "ingest_source_item"`, `EMBED_DOCUMENT_TASK = "embed_document"` (the task decorators use these).
  - `class IngestionRequestedPayload(TypedDict)` with `ingestion_run_id: str`; `class DocumentReadyPayload(TypedDict)` with `document_id: str` and `ingestion_run_id: str`.
  - `class EventRoute(NamedTuple)` with `task_name: str`, `queue: str`, `payload_keys: frozenset[str]` (from the TypedDict's annotations).
  - `EVENT_ROUTES: Mapping[str, EventRoute]` bound to a `types.MappingProxyType` (backlog `0065db9`).
  - `enqueue_source_item_ingestion_requested(*, db: Session, source_item_id: UUID, ingestion_run_id: UUID) -> OutboxEvent`.
- `app.ingestion.service.ingest_source_item(*, db: Session, ingestion_run_id: UUID, storage: StorageService, parser: Parser, settings: Settings) -> None` loads the run and its item; it fetches by the run's key, fails the run (`expected=FETCHING`, fingerprint copy) when `sha256(raw_bytes) != run.content_hash`, and writes `Document.raw_object_key` from the run.
- The Celery task is `ingest_source_item(*, ingestion_run_id: str)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_ingestion_requested_payload_carries_only_the_run_id` - the payload equals `{"ingestion_run_id": str(run_id)}`, and the run row holds the key and hash.
  - `test_fingerprint_mismatch_fails_the_run` - Garage holds `b"other bytes"` under the run's key; afterwards the run is `failed` with the fingerprint copy, `document_id` is None, and no chunks exist.
  - `test_older_run_uses_its_own_version` - seed run v1 (key k1, bytes v1), rewrite the item's `raw_object_key`/`content_hash` to v2 values (simulating S7), then ingest run v1: `document.raw_object_key == k1` and the chunk text comes from v1.
- [ ] **Step 2: Run to verify they fail.** Expected: FAIL (the payload still carries four keys; no fingerprint check).
- [ ] **Step 3: Implement** the columns, payload, service, task, and dispatcher payload use; update `seed_upload` and the dispatcher tests' payload helper.
- [ ] **Step 4: Run all backend gates; commit** - `feat(backend): pin each ingestion run to its file version`.
- [ ] **Step 5: Write the failing contract test** `test_task_signatures_match_event_payloads` - for every route, `celery_app.tasks[route.task_name]` exists and the keyword-only parameter names of its `run` equal `route.payload_keys`.
- [ ] **Step 6: Implement** the constants, TypedDicts, `EventRoute`, and `MappingProxyType`; the dispatcher reads `route.task_name`/`route.queue`. Gates green. Commit: `refactor(backend): type the outbox payload and task-name contract`.

---

### Task 6: Storage client lifecycle and error taxonomy

**Files:**
- Modify: `backend/app/storage/service.py`, `backend/app/storage/__init__.py`, `backend/app/sources/router.py`, `backend/app/workers/tasks.py`, `backend/app/ingestion/service.py` (`_fetch_raw_bytes` catches `StorageError`)
- Modify: `backend/tests/conftest.py` (one shared `storage` fixture replacing the two module copies)
- Test: `backend/tests/storage/test_service.py`, `backend/tests/sources/test_api.py`

**Interfaces:**
- `class StorageError(Exception)`; `class ObjectNotFoundError(StorageError)`; `class StorageUnavailableError(StorageError)`.
- `StorageService(*, settings: Settings)` builds its client from its own `boto3.session.Session()` with `Config(s3={"addressing_style": "path"}, connect_timeout=5, read_timeout=30, retries={"mode": "standard", "max_attempts": 3})`.
- `get_object` raises `ObjectNotFoundError` for a `ClientError` whose code is `NoSuchKey` or `404`, and `StorageUnavailableError` for every other client or botocore failure; `put_object` raises `StorageUnavailableError`.
- `get_storage() -> StorageService` (`@lru_cache`, built from `get_settings()`) is both the FastAPI dependency and the worker accessor. The router takes `storage: StorageService = Depends(get_storage)`; tests use `app.dependency_overrides[get_storage]`, never a module-symbol monkeypatch.

- [ ] **Step 1: Write the failing tests:**
  - `test_get_missing_key_raises_object_not_found` (replaces `test_get_missing_key_raises`, which pinned NoSuchKey as unavailable).
  - `test_unreachable_endpoint_raises_unavailable` - endpoint `http://127.0.0.1:1`.
  - `test_get_storage_returns_one_cached_service`.
  - `test_upload_storage_failure_returns_503` - the override's `put_object` raises `StorageUnavailableError`; expect 503 `Could not store the file. Please try again.` and no `source_items` row.
  - `test_storage_put_runs_with_no_open_transaction` moves to the dependency override.
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Client lifecycle** - `get_storage`, the client config, router/task wiring, and the shared fixture. Gates green. Commit: `refactor(backend): cache one configured storage client per process`.
- [ ] **Step 4: Error taxonomy** - the two subclasses and the fetch path. Gates green. Commit: `feat(backend): distinguish missing objects from unavailable storage`.

---

### Task 7: Failure reporting and write paths

**Files:**
- Modify: `backend/app/ingestion/service.py`, `backend/app/ingestion/models.py`, `0005` (constraint name), `backend/app/providers/stub_parser.py` (copy), `backend/app/providers/base.py` (`ParseError` docstring: its message is shown to users), `backend/app/providers/__init__.py` (`ParseError` joins `__all__`)
- Test: `backend/tests/ingestion/test_service.py`, `backend/tests/providers/test_stub_parser.py`

**Interfaces:**
- `_run_error_message(*, exc: BaseException) -> str` maps exceptions to the Global Constraints copy table, capped at 500 characters: `ParseError` returns its own message, the storage and fingerprint cases return their fixed copy, and anything else returns `Processing failed unexpectedly.`
- Every failure path calls `_logger.exception("ingestion run %s failed", run_id)` before recording the safe message (`_logger = logging.getLogger(__name__)`).
- The documents unique constraint is named `uq_documents_source_item_id_content_hash` (`0005` + ORM); the identical-version backstop runs only when `exc.orig.diag.constraint_name` equals it, and any other `IntegrityError` fails the run (backlog `3587104`).
- Embed: existence check via `select(Document.id)`; each batch writes its vectors with one ORM bulk UPDATE by primary key, `db.execute(update(Chunk), [{"id": ..., "embedding": ...}, ...])`.
- `Chunk.search_vector` and `Chunk.embedding` are `deferred=True`, and `Chunk.__mapper_args__ = {"eager_defaults": False}`, so a chunk INSERT no longer returns the tsvector.
- Docstrings say what is true: database errors propagate to the task (Task 10 retries them); every other failure ends on the run row.

- [ ] **Step 1: Write the failing tests:**
  - `test_missing_object_fails_the_run` - the run's key was never stored; expect `failed`, the object-missing copy (closes backlog `4447104`).
  - `test_unexpected_parser_error_is_logged_not_shown` - the parser fake raises `RuntimeError("SELECT secret FROM x")`; the run error is `Processing failed unexpectedly.`, and `caplog` holds an ERROR record with `exc_info` whose message contains the run id.
  - `test_embed_provider_failure_fails_the_run` - the provider fake raises; the run is `failed` from `indexing`, and every embedding is still None.
  - Update `test_garbage_pdf_fails_the_run`, `test_zero_chunk_document_fails_the_run`, and the stub parser tests to the new copy.
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Safe messages and logging.** Gates green. Commit: `feat(backend): record user-safe run errors and log the full failure`.
- [ ] **Step 4: Named backstop constraint.** Gates green (including `test_identical_version_conflict_is_idempotent_noop`). Commit: `fix(backend): reserve the identical-version backstop for its own constraint`.
- [ ] **Step 5: Write paths** (behavior-preserving; the existing embed tests cover it). In the same files: `search_vector` becomes `Mapped[str | None]` instead of `Mapped[Any]`, and the two lowercase-initial comments (`ingestion/models.py:63`, `ingestion/service.py:302`) are capitalized. Gates green. Commit: `perf(backend): slim the chunk insert and embed write paths`.

---

### Task 8: One upload source per project and the uploads API

**Files:**
- Modify: `0005`, `backend/app/sources/models.py`, `backend/app/sources/service.py`, `backend/app/sources/router.py`, `backend/app/sources/schemas.py`, `backend/tests/factories.py` (`seed_upload` reuses the project's upload source)
- Test: rename `backend/tests/sources/test_api.py` to `backend/tests/sources/test_uploads_api.py` (git mv); `backend/tests/sources/test_sanitize.py`; move `_auth`/`_default_team_id` into `backend/tests/helpers.py`

**Interfaces:**
- Schema: `uq_sources_project_id_upload` - a unique index on `sources (project_id) WHERE type = 'upload'`; the item unique becomes the named `uq_source_items_source_id_external_id`. `ix_sources_project_id` stays for S9's non-upload sources.
- `app.sources.service`:
  - `SUPPORTED_UPLOAD_TYPES: Mapping[str, str]` (a `MappingProxyType`): `.pdf` -> `application/pdf`, `.docx` -> `application/vnd.openxmlformats-officedocument.wordprocessingml.document`.
  - `upload_content_type(*, filename: str) -> str | None` - case-insensitive suffix lookup; the router's extension check uses it (its own `ALLOWED_EXTENSIONS` goes away).
  - `sanitize_filename` also strips C1 controls (`\x80-\x9f`) and rejects `.` and `..`.
  - `class DuplicateUploadError(Exception)`.
  - `@dataclass(frozen=True) class UploadListing` with `id: UUID`, `project_id: UUID`, `filename: str`, `status: RunStatus`, `created_at: datetime`.
  - `upload_file(*, db: Session, project_id: UUID, filename: str, content: bytes, storage: StorageService) -> UploadListing`.
  - `list_uploads(*, db: Session, project_id: UUID) -> list[UploadListing]` - newest first by item `created_at`, then `id`.
  - Removed: `create_upload_source`, `list_sources`, `SourceListItem`, and `SourceOut` from `schemas.py`.
- Router: `POST /projects/{project_id}/uploads` -> 201 `UploadOut`; `GET /projects/{project_id}/uploads` -> `list[UploadOut]`; one `_to_out(*, listing: UploadListing) -> UploadOut` mapper; `DuplicateUploadError` -> 409 with the copy; `UploadFile.size is None` -> 422 `The file size could not be determined.`; the 404/422/503 behavior is otherwise unchanged. The router passes `project.id` and never the ORM instance.
- `UploadOut` = `{id: UUID, project_id: UUID, filename: str, status: RunStatus, created_at: datetime}`, where `id` is the source item id.
- `SourceItem` docstring: a content item inside a source, identified by `external_id` (the filename for uploads), whose file fields describe its latest accepted version. This replaces "One uploaded content version", which contradicts U1.

`upload_file` flow (R2, R5, R6):
1. Pre-check in the read transaction: look up the project's upload item by `external_id == filename`. If it exists and is not retryable, raise `DuplicateUploadError` before storing anything. Retryable means its latest run status is `failed` and no `documents` row exists for it.
2. Hash the bytes, pick the item id (the existing one when retrying), build the key, `db.commit()`, then `storage.put_object(key=..., content=..., content_type=upload_content_type(filename=...))`.
3. Write transaction:
   - Get or create the upload source: `insert(Source).values(...).on_conflict_do_nothing(index_elements=[Source.project_id], index_where=Source.type == "upload")`, then select its id.
   - New name: insert the item and flush; an `IntegrityError` on `uq_source_items_source_id_external_id` rolls back and raises `DuplicateUploadError` (the race backstop).
   - Retry: lock the item with `with_for_update()`, re-check retryable (otherwise roll back and raise `DuplicateUploadError`), then update `content_hash`, `raw_object_key`, `size_bytes`, and `content_type`.
   - Then `request_ingestion(...)`, commit, and return the listing with status `queued`.

- [ ] **Step 1: Write the failing tests** (API level through `client`, seeds via `tests/factories.py`):
  - `test_upload_creates_item_run_and_event` - one `sources` row of type upload; the item carries `project_id` and `content_type`; the run is queued with its key and hash; the event payload is `{"ingestion_run_id": ...}`; the Garage object bytes match.
  - `test_uploads_share_the_project_upload_source` - two names give one `sources` row and two items.
  - `test_duplicate_filename_in_flight_is_rejected` - a second `report.pdf` while the first is queued -> 409 with the copy; still one item and one run.
  - `test_failed_file_can_be_uploaded_again` - claim then `mark_failed` the first run; re-upload `report.pdf` with new bytes -> 201 with the same `id`, two runs (latest queued), and the item's `content_hash` updated.
  - `test_indexed_file_cannot_be_replaced_yet` - an item with a document whose latest run failed -> 409.
  - `test_content_type_comes_from_the_extension` - the client sends `text/html` for `report.pdf`; the item and Garage `head_object` both say `application/pdf`.
  - `test_extension_check_is_case_insensitive` - `REPORT.PDF` -> 201.
  - `test_uploads_list_derives_the_latest_status` - two runs with explicit `created_at` give the newest status; a tie gives one row.
  - `test_c1_controls_are_dropped` and `test_dot_names_are_rejected` in `test_sanitize.py`.
  - Port the existing tests to `/uploads`: no open transaction during the PUT, the 422 validations, filename sanitization, editor role, public viewer (list ok, upload 404), project-delete cascade, and the 503.
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Upload source and identity** - schema, `upload_file`, `list_uploads`, router, schemas, factories. Gates green. Commit: `feat(backend): give each project one upload source with filename identity`.
- [ ] **Step 4: Content type from the extension.** Gates green. Commit: `fix(backend): derive the stored content type from the file extension`.
- [ ] **Step 5: Filename hardening** (C1 controls, dot names, unknown size). The unknown-size branch has no test: Starlette always sets `size` on parsed multipart parts, so the branch is defensive. Gates green. Commit: `fix(backend): reject dot names, C1 controls, and unknown sizes in uploads`.

---

### Task 9: Outbox backoff and dispatcher hardening

**Files:**
- Modify: `0005`, `backend/app/outbox/models.py`, `backend/app/core/config.py`, `backend/app/workers/dispatcher.py`
- Test: `backend/tests/workers/test_dispatcher_integration.py`, `backend/tests/test_config.py`

**Interfaces:**
- Schema: `outbox_events.next_attempt_at timestamptz NOT NULL DEFAULT now()`; `ix_outbox_events_next_attempt_at_unpublished` on `(next_attempt_at) WHERE published_at IS NULL` replaces `ix_outbox_events_created_at_unpublished`.
- Settings: `outbox_retry_base_seconds`, `outbox_retry_max_seconds`, `outbox_publish_timeout_seconds` (Global Constraints values).
- `app.workers.dispatcher`:
  - `@dataclass(frozen=True) class Backoff` with `base_seconds: float`, `max_seconds: float`, and `delay_seconds(self, *, attempts: int) -> float` returning `min(base_seconds * 2 ** (attempts - 1), max_seconds)`.
  - `@dataclass(frozen=True) class BatchResult` with `selected: int`, `published: int`.
  - `dispatch_batch(*, db: Session, app: Celery, batch_size: int, backoff: Backoff, publish_timeout_seconds: float) -> BatchResult` selects due rows (`published_at IS NULL AND next_attempt_at <= now()`, ordered by `next_attempt_at, id`, `FOR UPDATE SKIP LOCKED`). It publishes with `task_id=str(row.id)`, `timeout=` and `confirm_timeout=` set to the publish timeout. Every failure increments `attempts`, records `last_error`, and sets `next_attempt_at = now() + delay`. An unroutable row is backed off and the batch continues; a failed publish is backed off and ends the batch.
  - `run_loop(*, app: Celery, settings: Settings, session_factory: Callable[[], AbstractContextManager[Session]], sleep: Callable[[float], None], max_ticks: int | None = None) -> None`. Each tick runs inside `try`/`except Exception` with `_logger.exception`. The ready line goes to stderr once, after the first successful tick. The loop sleeps only when `selected < batch_size`. `main()` calls it with `session_scope` and `time.sleep`.

- [ ] **Step 1: Write the failing tests:**
  - `test_backoff_delay_doubles_and_caps` - `Backoff(1.0, 300.0)`: attempts 1 -> 1.0, 2 -> 2.0, 10 -> 300.0.
  - `test_publish_failure_backs_off_the_row` - after a patched failure: `attempts == 1`, `last_error` set, `next_attempt_at` later than the transaction's `now()`; an immediate second batch selects nothing.
  - `test_backed_off_row_does_not_block_rows_behind_it` - the oldest row fails; the next batch publishes the healthy row behind it.
  - `test_unroutable_rows_cannot_starve_the_outbox` - `batch_size=2`, three unroutable rows older than one valid row; within two batches the valid row is published.
  - `test_published_task_id_is_the_outbox_row_id` - the drained message's `id` header equals the row id.
  - `test_loop_survives_a_failing_tick` - the session factory raises `OperationalError` on the first tick and then works; with `max_ticks=2` the second tick publishes, and stderr holds exactly one `dispatcher ready`.
  - `test_loop_skips_sleep_after_a_full_batch` - a recording `sleep` is not called after a tick that selected `batch_size` rows.
  - Update the existing dispatcher tests to `BatchResult` and the new signature.
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Backoff** (schema, settings, selection, bump). Gates green. Commit: `feat(backend): back off failing outbox rows so they cannot starve the queue`.
- [ ] **Step 4: Publish bounds and task ids.** Gates green. Commit: `feat(backend): bound outbox publishes and tag tasks with their row id`.
- [ ] **Step 5: Loop tolerance** (`run_loop`, the ready line after the first successful tick, no sleep after a full batch). Gates green. Commit: `fix(backend): keep the dispatcher loop alive across failing ticks`.

---

### Task 10: Worker hardening and settings validation

**Files:**
- Create: `backend/app/workers/signals.py`, `backend/tests/fakes.py` (the shared mismatched embedding provider, replacing the copies in `test_service.py`/`test_schema_guard.py` and `test_celery_app.py`)
- Modify: `backend/app/core/db.py`, `backend/app/core/config.py`, `backend/app/providers/__init__.py`, `backend/app/workers/celery_app.py`, `backend/app/workers/tasks.py`
- Test: `backend/tests/test_db.py`, `backend/tests/test_config.py`, `backend/tests/workers/test_celery_app.py`

**Interfaces:**
- `app.core.db`: `make_engine(*, database_url: str) -> Engine` passes `pool_pre_ping=True`; a module-level `engine` backs `SessionLocal`; the module docstring names both session helpers.
- `app.workers.celery_app.make_celery_app(*, broker_url: str) -> Celery` adds `task_queues` (durable `Queue(INGESTION_QUEUE)` and `Queue(EMBED_QUEUE)`), `task_default_queue = INGESTION_QUEUE`, `broker_connection_retry_on_startup = True`, and `include=["app.workers.tasks", "app.workers.signals"]`. The module imports neither `app.ingestion` nor `app.providers`. Celery imports `include` modules (`loader.init_worker`) before sending `worker_init` (`celery/worker/worker.py` lines 94 and 127, verified), so the handlers connect in time.
- `app.workers.signals`: the `worker_init` handler resolves both `get_parser` and `get_embedding_provider` and runs `run_startup_checks`, all inside the `SystemExit` guard, then calls `engine.dispose()` so no guard connection outlives boot (prefork-safe). The `worker_ready` ready line moves here unchanged.
- Tasks: both use `autoretry_for=(OperationalError, InterfaceError)` (from `sqlalchemy.exc`), `retry_backoff=True`, `retry_backoff_max=60`, `retry_jitter=True`, `max_retries=5`.
- Settings: `parser_provider: Literal["stub"]` and `embedding_provider: Literal["stub"]`; the factories use `match` with `typing.assert_never`. A model validator requires `0 <= chunk_overlap_tokens < chunk_target_tokens <= chunk_max_tokens`, and the production validator also rejects the default `s3_secret_key` (`rag-dev-secret-local`).

- [ ] **Step 1: Write the failing tests:**
  - `test_engine_pings_connections_before_use` - `make_engine(...).pool._pre_ping is True`.
  - `test_tasks_retry_transient_database_errors` - both registered tasks list `OperationalError` and `InterfaceError` in `autoretry_for`, with `max_retries == 5`.
  - `test_dispatcher_does_not_import_the_pipeline` - in a subprocess, after `import app.workers.dispatcher`, neither `app.ingestion.service` nor `pypdf` is in `sys.modules`.
  - `test_worker_init_refuses_when_provider_resolution_fails` - a patched `get_parser` raises `ValueError`; the handler raises `SystemExit`.
  - `test_celery_app_declares_both_queues`.
  - `test_unknown_provider_setting_is_rejected`, `test_chunk_budgets_must_be_ordered` (overlap >= target, and target > max), `test_production_rejects_default_s3_secret`.
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3:** `pool_pre_ping` and the module engine. Gates green. Commit: `fix(backend): ping pooled connections before use`.
- [ ] **Step 4:** Task autoretry. Gates green. Commit: `fix(backend): retry tasks on transient database errors`.
- [ ] **Step 5:** `signals.py` split, `engine.dispose()`, `tests/fakes.py`. Gates green. Commit: `refactor(backend): split worker signal handlers from the Celery app`.
- [ ] **Step 6:** Provider literals and guarded resolution. Gates green. Commit: `fix(backend): refuse to boot on an unresolvable provider`.
- [ ] **Step 7:** Queue declarations. Gates green. Commit: `feat(backend): declare the worker queues in the app config`.
- [ ] **Step 8:** Chunk-budget and production-secret validation. Gates green. Commit: `fix(backend): validate chunk budgets and the production storage secret`.

---

### Task 11: Durable broker state and chores

**Files:**
- Modify: `deploy/docker-compose.yml`, `backend/scripts/broker_admin.py`, `backend/pyproject.toml`, `README.md` (runbook note)

**Interfaces:**
- Compose `rabbitmq`: `hostname: rabbitmq`, named volume `rabbitmqdata:/var/lib/rabbitmq`, healthcheck `["CMD", "rabbitmq-diagnostics", "-q", "ping"]` (interval 10s, timeout 10s, retries 10).
- `broker_admin.py`: every `urlopen` call passes `timeout=10`.
- `pyproject.toml`: `boto3`, `pgvector`, `python-multipart`, `pypdf`, `python-docx` get `>=` floors at the installed major.minor (read with `..\.venv\Scripts\python.exe -m pip show <name>`).

- [ ] **Step 1: Prove broker state survives a recreate.** After the compose change, run `docker compose -f deploy/docker-compose.yml up -d --force-recreate rabbitmq`, then `docker compose -f deploy/docker-compose.yml exec rabbitmq rabbitmqctl add_vhost durability_probe`, recreate again with the same `up` command, and run `rabbitmqctl list_vhosts`. Expected: `durability_probe` is listed. Remove it with `rabbitmqctl delete_vhost durability_probe`. The README runbook notes that this change discards the old anonymous broker volume once; `rag_test` and `rag_e2e` are recreated by their bootstraps. Commit: `fix(deploy): persist RabbitMQ state across container recreation`.
- [ ] **Step 2:** Broker admin timeout. Backend gates green. Commit: `fix(backend): time out broker admin calls`.
- [ ] **Step 3:** Dependency floors; `pip check` clean; backend gates green. Commit: `chore(backend): add lower bounds to the S3 dependencies`.

---

### Task 12: Frontend uploads API and the project page split

**Files:**
- Create: `web/src/features/uploads/uploadsApi.ts`, `uploadRules.ts`, `uploadStatus.ts`, `useProjectUploads.ts`, `UploadCard.tsx`, `UploadsTable.tsx`, and tests `uploadRules.test.ts`, `uploadStatus.test.ts`, `UploadCard.test.tsx`
- Delete: `web/src/features/sources/sourcesApi.ts`
- Modify: `web/src/app/api.ts` (tag `"Source"` becomes `"Upload"`), `web/src/features/projects/ProjectPage.tsx`, `ProjectPage.test.tsx`, `web/src/test/handlers.ts`, `web/src/app/App.test.tsx` (the stale comment from backlog `347efdc`)

**Interfaces:**
- `uploadsApi.ts`:
  - Types: `UploadStatus` (the six values) and `Upload = { id; project_id; filename; status: UploadStatus; created_at }`, with no `type` field (this resolves the backlogged MSW `"document"` fixture).
  - Endpoints: `getUploads` (`/projects/${projectId}/uploads`, `providesTags: [{ type: "Upload", id: projectId }]`) and `uploadFile` (multipart POST, invalidating the same tag).
  - Exports: `useGetUploadsQuery`, `useUploadFileMutation`. The cache selector stays private to `useProjectUploads`.
- `uploadRules.ts`: `MAX_UPLOAD_MB = 25`, `ALLOWED_EXTENSIONS`, and `uploadRejection(file: File): string | null`, which adds the empty-file check.
- `uploadStatus.ts`: `isTerminal(status)`, `statusChip(status)` (moved unchanged).
- `useProjectUploads(projectId: string | undefined, options: { skip: boolean }): { uploads: Upload[] | undefined; isLoading: boolean; error: unknown; refetch: () => void }`. It owns the polling decision (2s while any row is non-terminal; 0 once all are terminal or an uncached fetch failed). It uses one memoized selector per `projectId` for both data and error, created once per `projectId`, not on every store update.
- `UploadCard({ projectId }: { projectId: string })` owns the mutation, client checks, and alert (the server's 409/422/503 detail through `getErrorMessage`). Its copy derives the limit from `MAX_UPLOAD_MB`, and the label Button sets `tabIndex={-1}`, so the hidden input is the only tab stop.
- `UploadsTable({ uploads }: { uploads: Upload[] })` renders rows and the empty state; the dead `data-testid="skeleton-row"` goes.
- `ProjectPage` composes the header, `UploadCard`, and the uploads section (skeleton, error, or table).

- [ ] **Step 1: Contract switch** - write the failing changes first: point the MSW handlers and every `ProjectPage.test.tsx` route at `/projects/p-1/uploads`, and add `shows the server's 409 copy when the filename already exists`. Run `npm run test`. Expected: FAIL. Implement `uploadsApi.ts`, delete `sourcesApi.ts`, update the page imports. Web gates green. Commit: `feat(web): switch the project page to the uploads API`.
- [ ] **Step 2: Page split** - write `uploadRules.test.ts` and `uploadStatus.test.ts` (chip colors are asserted there; `ProjectPage.test.tsx:118-120` stops asserting MUI class names and checks chip labels). Then extract the modules and components above; every existing `ProjectPage` behavior test stays green unchanged apart from the class-name assertion. Web gates green. Commit: `refactor(web): split the project page into upload card, uploads table, and polling hook`.
- [ ] **Step 3: Client fixes** - write failing tests `rejects an empty file without posting` and `the upload control is a single tab stop` (tab from the back link reaches the file input exactly once before the table), then implement. Web gates green. Commit: `fix(web): reject empty files client-side and keep one tab stop for upload`.

---

### Task 13: E2E journey

**Files:**
- Modify: `web/e2e/journey.spec.ts`

- [ ] **Step 1: Extend the upload journey.** After both rows show `Ready`, upload `tiny.pdf` again and expect `page.getByRole("alert")` to contain `A file with this name already exists in this project.`, with the row count unchanged (two).
- [ ] **Step 2: Run** `npm run e2e` from `web/` (compose up, no dev worker needed thanks to vhost isolation). Expected: every journey and enforcement test passes.
- [ ] **Step 3: Commit** - `test(e2e): prove the duplicate-filename rejection through the browser`.

---

### Task 14: Docs, backlog, and final verification

**Files:**
- Modify: `docs/superpowers/specs/2026-10-12-s3-upload-ingestion-design.md`, `docs/superpowers/specs/2026-10-06-rag-mvp-slices-design.md`, `README.md`, `backend/app/ingestion/__init__.py`, `backend/app/outbox/__init__.py`, `docs/superpowers/backlog.md`

- [ ] **Step 1: Amend the S3 spec** to describe what is built:
  - Status line: "amended by the 2026-10-14 review fixes".
  - Decision 2: transient database errors retry; pre-ping.
  - Decision 3 and section 5.2: backoff, `next_attempt_at`, publish timeouts, `task_id`, loop tolerance.
  - Decision 7 #9: the S3 retry path for failed items without a document.
  - Decision 11: U1, the 409 rule, case-sensitive identity.
  - Decision 12: the correlated latest run with the id tie-break.
  - Decision 13: R4.
  - Section 3.4 layout: `app/models.py`, `ingestion/status.py`, `runs.py`, `schema_guard.py`, `workers/signals.py`.
  - Section 4.1: the composite chain, the run version columns, the outbox column, the partial unique index, the named constraints and new checks.
  - Section 4.3: indexes.
  - Section 5.1: the `upload_file` flow and content type.
  - Sections 5.3/5.4: run-pinned fetch, fingerprint check, safe errors.
  - Section 6: the `/uploads` endpoints and `UploadOut`.
  - Section 7: the frontend modules.
  - Section 10: the remaining stuck-run causes (database loss after the claim, broker loss before consumption on a non-persistent setup).
  - Commit: `docs(specs): amend the S3 spec with the review fixes`.
- [ ] **Step 2: Slices spec:**
  - Status line: S0-S3 implemented.
  - The S3 heading gets the done mark S2 has.
  - Deferred decision #4 row: the provider constant, not a setting.
  - The S0 row's MinIO mention gets "(replaced by Garage in S3)".
  - The S7 row says file delete and replace instead of source delete.
  - The closing "Next:" line names S4.
  - Commit: `docs(specs): bring the slices spec up to date with S3`.
- [ ] **Step 3: README:**
  - The intro names ingestion as done.
  - Test prerequisites: Garage is needed by the storage, uploads, and ingestion suites.
  - The runbook mentions the `/uploads` API and the RabbitMQ volume.
  - Package docstrings: ingestion becomes "Documents, chunks, ingestion runs, and the ingest and embed pipeline."; outbox becomes "The transactional outbox: event rows, payload contracts, and routing."
  - Commits: `docs: refresh the README for the S3 runbook and test prerequisites`, then `docs(backend): correct stale package docstrings`.
- [ ] **Step 4: Backlog.**
  - Remove the entries this plan resolves: `0065db9`, the `3587104` items, the `09a3c8c` items, the `81f8d8c` items except the attempts cap, the `347efdc` items except `node-buffer.d.ts`, the `f4ef110` item, the final-review extras about size copy, dot names, `urlopen`, and the MSW type, plus the Task 8 and Task 12 sections.
  - Fix the "also recorded above" pointer by merging every remaining S3 entry into one `## 2026-10-14 - S3 review fixes (s3-upload-ingestion)` section with commit links.
  - Add the deferred items:
    - Upload body size enforced only after Starlette spools the body (needs a Content-Length guard or a proxy limit before any exposed deployment).
    - Prefork readiness: `task_reject_on_worker_lost` with a delivery limit for embed.
    - `worker_prefetch_multiplier=1` and separate worker processes per queue before S5's network providers.
    - Embed re-delivery re-embeds every chunk (filter `embedding IS NULL` or skip non-`indexing` runs before paid providers).
    - The identical-version backstop marks a run `ready` against a document that may be half-embedded or inactive (S7).
    - A partial unique index allowing one in-flight run per item, together with the S7 sweep; the sweep must also cover `queued` runs whose event was published.
    - Outbox attempts cap, dead-lettering, and published-row retention (S7).
    - S4 retrieval notes: HNSW `ef_search` and `iterative_scan`, `embedding IS NOT NULL` in the vector leg, pin the `pgvector/pgvector` image tag.
    - S5: record `embedding_model` per vector; prefer a side-by-side column over an in-place dimension change.
    - S9: the listing must aggregate multi-item sources, and source-level sync failures need a home.
    - Same-name uploads differing only in case are distinct files.
    - The parser, service, and chunker all guard empty documents with different messages (consolidate at S5).
    - Viewer upload 404 copy, a live region for status changes, and the stale-data snackbar parity with `ProjectsPage`.
    - The UI says "documents" for uploads while the backend's `documents` are parsed versions.
    - A two-session `SKIP LOCKED` dispatcher test and closing each test's Celery app.
    - Time-ordered `uuid7` primary keys (house-wide).
    - Optional cheap checks: `jsonb_typeof(heading_path) = 'array'`; `NormalizedElement.type` as a `Literal` before S5's Unstructured swap.
    - Compose ports bind every interface with fixed credentials; the production validator ignores the `guest` broker URL.
    - `4359933` mixed the FK-index test fix into the schema commit, and `e3f24cc` is its fixup; history is left as is.
  - Commit: `docs(backlog): reconcile the S3 entries after the review fixes`.
- [ ] **Step 5: Final verification** - all backend and web gates, then `npm run e2e`, on the final tree. Expected: all green; record the counts.

## Post-plan

- Fresh-context whole-branch review of `5df2954..HEAD` (AGENTS.md), focused on the rulings above. Then superpowers:finishing-a-development-branch to merge `s3-upload-ingestion` into `master`.
- After the merge, re-run the shared venv's editable install from the main repo (S3 backlog note) and `alembic upgrade head` on the dev database (it is at `0004`).
