# S3 - Upload & Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the full offline ingestion pipeline - PDF/DOCX upload from the browser into Garage, Celery-driven parse -> normalize -> chunk -> embed with stub providers, a transactional outbox over real RabbitMQ, pgvector/FTS indexes - plus the project page with upload and processing status, so a real PDF travels `queued` -> `ready` fully offline.

**Architecture:** The upload API transaction writes `sources` + `source_items` + an `ingestion_runs` row and a `source_item_ingestion_requested` outbox row; a standalone dispatcher loop publishes outbox rows to Celery queues after broker confirms; thin Celery tasks wrap claim-guarded `app/ingestion/service.py` functions that parse via stub providers, chunk, and commit document + chunks + the next outbox event in one transaction; the embed task batches vectors in place and marks the run `ready`. Source status is always derived from the item's latest run, never stored. The frontend adds a guarded `/projects/:projectId` route with an upload card and an RTK Query-polling sources table.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic + Postgres 17 (pgvector) + Celery >= 5.6 (RabbitMQ broker, kombu ships with it) + boto3 (Garage S3 API) + pypdf/python-docx stub providers; React 19 + RTK Query + MUI in the Devias style + Vitest/MSW + Playwright 1.64.

**Spec:** `../specs/2026-10-12-s3-upload-ingestion-design.md` (two review rounds applied; the plan argues from the spec, so executors read both).

## Global Constraints

- Execute in a dedicated worktree/branch (AGENTS.md); one concern per commit; every task ends with the gates below green before its commit.
- Backend gates (run from `backend/`): `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest`. Web gates (from `web/`): `npm run lint`, `npm run format:check`, `npm run test`, `npm run build`. `npm run e2e` is a separate gate, never in the default run.
- pytest and e2e need the compose services up: `docker compose -f deploy/docker-compose.yml up -d` (db, rabbitmq, garage). Real services, no mocking of storage or broker; the two spec-prescribed patched captures (upload transaction state, dispatcher publish failure) are instrumentation around the real thing.
- Python style: keyword-only parameters (`PLR0917`), line length 110, docstrings on every module/class/function followed by a blank line, comments start with a capital and end with a dot, never the em dash (use " - "). Alembic scripts are exempt from docstring rules.
- Windows: venv at repo root; from `backend/` invoke `..\.venv\Scripts\python.exe`. Worker runs `--pool=solo` (prefork unsupported); embedded Beat refused outright; the dispatcher is a plain process (`python -m app.workers.dispatcher`).
- Exact values from the spec: `STUB_EMBEDDING_DIM = 384`; `chunks.embedding vector(384)` hardcoded in the migration (never a runtime value); chunk settings 600/1000/80; `embedding_batch_size` 64; `outbox_poll_interval_seconds` 1.0, `outbox_batch_size` 20; `max_upload_mb` 25; object key `raw/{project_id}/{source_item_id}/{content_hash}/{filename}`; statuses `queued|fetching|processing|indexing|ready|failed`; queue names `ingestion`/`embed`; task names `ingest_source_item`/`embed_document`; broker vhosts `/` (dev), `rag_test` (pytest), `rag_e2e` (e2e); S3 defaults endpoint `http://localhost:3900`, access key `rag-dev-key`, secret `rag-dev-secret-local` (mirrors compose), region `garage`, bucket `rag-dev`.
- Event payloads carry only string ids: `source_item_ingestion_requested` -> `{"source_item_id", "ingestion_run_id", "raw_object_key", "content_hash"}`; `document_ready_for_embedding` -> `{"document_id", "ingestion_run_id"}`.
- `SourceOut = {id, project_id, type, status, filename, created_at}`; errors use FastAPI's `{detail}` shape; 404 hides both missing and forbidden.
- Frontend: TypeScript strict, no `any`, ESLint `--max-warnings 0`, Prettier width 100, no `.skip`/`.only`/`.todo` in tests; plain professional English copy; Devias continuity (accent `#5664D2`, 12px cards, 1px borders); pages never build URLs or parse response bodies (S2 deep-module rule).
- Provider rule: parsers return `NormalizedDocument`; provider-specific objects never cross the `providers/` boundary.
- Statuses and derived fields: `ingestion_runs.status` is the only stored status; every transition is `UPDATE ... WHERE id = :run_id AND status = :expected` (`fetching`/`processing` expected on ingestion failure, `indexing` on embed failure).

## Review Focus

Failure modes the spec implies but whose tasks could under-exercise; each is pinned by a test in the owning task.

1. **Re-delivered ingestion message after the run moved on** - must ack no-op, never re-claim or clobber: Task 8 (`test_duplicate_delivery_no_ops`, `test_missing_run_no_ops`).
2. **Hostile upload filenames** (traversal, control characters, empty basename) - sanitized or 422, never a key with separators: Task 9 (sanitize unit tests + `test_upload_filename_sanitized`).
3. **Broker unreachable during dispatch** - the row keeps its `attempts`/`last_error` bump and is retried next tick, never lost: Task 10 (`test_publish_failure_bumps_and_retries`).
4. **Oversize upload** - rejected with a friendly 422 without reading the bytes: Task 9 (`test_upload_validates_extension_empty_and_size` with a 26MB body).
5. **Unextractable document** (scanned/garbage PDF, headings-only file) - run `failed` with a clear message, never a silent zero-chunk document: Task 4 (`ParseError` on zero elements), Task 5 (`test_empty_element_list_raises`, `test_headings_only_document_yields_zero_chunks`), Task 8 (`test_garbage_pdf_fails_the_run`, `test_zero_chunk_document_fails_the_run`).

## Task dependency graph

The default execution (subagent-driven development) is one implementer at a time; the waves below are an optimization that the AGENTS.md worktree rule permits, under the isolation rules listed here. When in doubt, run a wave sequentially - the graph still saves re-planning.

### Direct dependencies

| Task | Directly consumes | Notes |
|---|---|---|
| 1 | nothing | Pre-flight: merges before any parallel backend wave (its Step 7 makes concurrent suite runs safe) |
| 2 | nothing | Gates every backend task: installs all dependencies, adds the settings, stands up Garage |
| 3 | 1 (env.py edit), 2 (`pgvector` dependency) | |
| 4 | 2 (settings fields, pypdf, python-docx) | |
| 5 | 4 (`NormalizedElement`) | |
| 6 | 2 (S3 settings, boto3, compose Garage up) | |
| 7 | 3 (`OutboxEvent`) | |
| 8 | 3, 4, 5, 6, 7 | The convergence point of the backend pipeline |
| 9 | 3, 6, 7, 8 (plus 2: `python-multipart`) | |
| 10 | 7, 8 (plus 2: `celery` dependency) | Also produces `ensure_broker_vhost`, which 12 reuses |
| 11 | nothing | Vitest/MSW mocks the spec contract; the only coupling to 9 is the `SourceOut` shape both take verbatim from the spec, and e2e (12) is the backstop |
| 12 | 3 (truncate list), 8, 9, 10, 11 (plus 4: `tiny.pdf`) | Whole-system run; exclusive ports and environment |
| 13 | 12 | Final gates plus docs; everything else transitively |

### Waves

| Wave | Tasks (dispatch together) | Implementer tier | Why they are safe together |
|---|---|---|---|
| 0 | 1 + 11 | cheap + standard | Disjoint worlds: alembic tests vs vitest (no Postgres involved in 11) |
| 1 | 2 | standard | The only pip-install task; worktrees share the root `.venv` |
| 2 | 3 + 4 + 6 | standard | Disjoint files: models+migration / providers+fixtures / storage |
| 3 | 5 + 7 | standard | Disjoint files: chunker / outbox events |
| 4 | 8 | most capable | Convergence point; the transactional correctness lives here |
| 5 | 9 + 10 | standard + capable | Disjoint files: sources API+router / workers+dispatcher+conftest |
| 6 | 12 | most capable | Real stack, exclusive ports (8001/5173), `rag_e2e` DB and vhost |
| 7 | 13 | cheap | Docs plus the full gate run |

Critical chain: 1 -> 2 -> 3 -> 7 -> 8 -> 10 -> 12 -> 13 (8 waves). Tasks 4+5, 6, 9, and 11 all hide in that chain's slack.

```mermaid
flowchart TD
    subgraph W0["Wave 0"]
        T1["1 - alembic test safety"]
        T11["11 - frontend project page"]
    end
    subgraph W1["Wave 1"]
        T2["2 - settings, deps, Garage"]
    end
    subgraph W2["Wave 2"]
        T3["3 - models + migration 0005"]
        T4["4 - stub providers"]
        T6["6 - storage service"]
    end
    subgraph W3["Wave 3"]
        T5["5 - chunker"]
        T7["7 - outbox events"]
    end
    subgraph W4["Wave 4"]
        T8["8 - pipeline services + guard"]
    end
    subgraph W5["Wave 5"]
        T9["9 - upload + sources API"]
        T10["10 - worker + dispatcher"]
    end
    subgraph W6["Wave 6"]
        T12["12 - Playwright journey"]
    end
    subgraph W7["Wave 7"]
        T13["13 - docs + final gates"]
    end

    T1 -. "env.py edit" .-> T3
    T2 --> T3
    T2 --> T4
    T2 --> T6
    T4 --> T5
    T3 --> T7
    T3 --> T8
    T4 --> T8
    T5 --> T8
    T6 --> T8
    T7 --> T8
    T6 --> T9
    T7 --> T9
    T8 --> T9
    T7 --> T10
    T8 --> T10
    T9 --> T12
    T10 --> T12
    T11 --> T12
    T3 --> T12
    T12 --> T13
```

### Parallel execution rules

- No two backend suite runs before Task 1 merges: its Step 7 derives the alembic scratch database names from `RAG_TEST_DATABASE_URL`. Before that change, two concurrent `pytest` runs drop each other's scratch databases mid-test.
- One worktree per task, and every backend worktree in a parallel wave sets its own `RAG_TEST_DATABASE_URL` (e.g. `rag_test_t4`); conftest honors it, and after Task 1 the scratch databases derive from it too.
- Siblings in a wave touch disjoint files (verified per wave above). Merge serially into the integration branch in wave order and re-run the four backend gates after every merge - a merge can break gates even when each branch was green on its own.
- Shared services: the Garage bucket is shared safely by design (UUID keys, spec section 3.2); RabbitMQ is touched by exactly one task per point in time (10 on the `rag_test` vhost, 12 on `rag_e2e`); the root `.venv` is shared and only Task 2 installs into it, before any wave that needs the packages.
- Only Task 11 runs vitest, so the known jsdom starvation under concurrent vitest suites (backlog, 2026-10-12) cannot bite.
- Per-task reviews still gate every task; the whole-branch review stays at the end (Post-slice).

---

### Task 1: Alembic test-infrastructure safety

Two concerns, each in its own commit: the stray `RAG_DATABASE_URL` override (the pre-existing backlog hazard; spec section 8 says it lands first) and deriving the alembic scratch databases from the configured test URL so parallel worktree suite runs cannot collide - the enabler for the parallel waves in the "Task dependency graph" section.

**Files:**
- Modify: `backend/alembic/env.py` (remove the `os.environ["RAG_DATABASE_URL"]` override)
- Modify: `backend/tests/test_alembic.py`
- Modify: `docs/backlog.md` (drop the resolved 2026-10-12 entry)

**Interfaces:**
- Consumes: the existing `engine` fixture and `DEFAULT_TEST_URL`.
- Produces: `alembic upgrade` always uses the configured `sqlalchemy.url` (every caller - conftest, e2e_db.py, alembic.ini - sets it explicitly); the two scratch databases are named after the configured test database (`rag_test_downgrade` -> `<test-db>_downgrade`, `rag_test_0002_backfill` -> `<test-db>_0002_backfill`), so a worktree running the suite with its own `RAG_TEST_DATABASE_URL` owns its scratch databases too.

- [ ] **Step 1: Write the failing test**

In `tests/test_alembic.py` (needs `import pytest` if absent):

```python
def test_upgrade_ignores_stray_database_url_env(
    *, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check that a stray RAG_DATABASE_URL cannot redirect a configured migration run."""

    monkeypatch.setenv("RAG_DATABASE_URL", "postgresql+psycopg://rag:rag@no-such-host:5432/rag_poison")
    url = os.environ.get("RAG_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    # The engine fixture already migrated to head, so this is a no-op run.
    command.upgrade(config, "head")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `..\.venv\Scripts\python.exe -m pytest tests/test_alembic.py::test_upgrade_ignores_stray_database_url_env -v`
Expected: FAIL with a connection error against `no-such-host` (env.py currently honors the env var).

- [ ] **Step 3: Implement**

Delete the `if os.environ.get("RAG_DATABASE_URL"): ...` block (and the `os` import) from `backend/alembic/env.py`. All callers set `sqlalchemy.url` explicitly; nothing else reads that env var for migrations.

- [ ] **Step 4: Run test to verify it passes**

Run: same command. Expected: PASS.

- [ ] **Step 5: Full backend verification**

Run: `ruff check .`; `ruff format --check .`; `mypy app tests`; `pytest`.
Expected: all green.

- [ ] **Step 6: Remove the resolved backlog entry and commit**

Remove the `backend/alembic/env.py` item from `docs/backlog.md` (it is now fixed).

```bash
git add alembic/env.py tests/test_alembic.py docs/backlog.md
git commit -m "fix(backend): make alembic ignore a stray RAG_DATABASE_URL"
```

- [ ] **Step 7: Derive the scratch database names from the configured test URL**

In `tests/test_alembic.py`, `test_migrations_downgrade_to_base` uses the fixed name `rag_test_downgrade` and `test_0002_downgrade_backfills_is_personal` uses `rag_test_0002_backfill`. Both drop-then-create, so two suite runs executing them at the same time on the same Postgres destroy each other's scratch database. Change each to derive the name from the configured URL, e.g. `db_name = f"{url.rsplit('/', 1)[1]}_downgrade"` (and `..._0002_backfill`). Combined with a per-worktree `RAG_TEST_DATABASE_URL`, a parallel wave's suite runs own disjoint databases end to end; the existing tests cover the behavior, no new tests.

- [ ] **Step 8: Full backend verification and commit**

Run: `ruff check .`; `ruff format --check .`; `mypy app tests`; `pytest`.
Expected: all green.

```bash
git add tests/test_alembic.py
git commit -m "test(backend): derive alembic scratch databases from the configured test URL"
```

---

### Task 2: Settings, dependencies, and the Garage compose service

**Files:**
- Modify: `backend/app/core/config.py`, `backend/pyproject.toml`, `backend/tests/test_config.py`
- Modify: `deploy/docker-compose.yml`; Create: `deploy/garage.toml`
- Modify: `docs/backlog.md` (drop the resolved MinIO item)

**Interfaces:**
- Consumes: nothing new.
- Produces (later tasks read these from `Settings`): `broker_url: str = "amqp://guest:guest@localhost:5672//"`, `s3_endpoint: str = "http://localhost:3900"`, `s3_access_key: str = "rag-dev-key"`, `s3_secret_key: str = "rag-dev-secret-local"`, `s3_region: str = "garage"`, `s3_bucket: str = "rag-dev"`, `parser_provider: str = "stub"`, `embedding_provider: str = "stub"`, `chunk_target_tokens: int = 600`, `chunk_max_tokens: int = 1000`, `chunk_overlap_tokens: int = 80`, `embedding_batch_size: int = 64`, `outbox_poll_interval_seconds: float = 1.0`, `outbox_batch_size: int = 20`, `max_upload_mb: int = 25`. Compose runs `garage` on 3900 (S3) + 3903 (admin) with those credentials and a `rag-dev` bucket.

- [ ] **Step 1: Write the failing settings tests**

In `tests/test_config.py`:

```python
def test_ingestion_settings_defaults() -> None:
    """The S3 pipeline settings default to the compose services and the stub providers."""

    s = Settings(_env_file=None)
    assert s.broker_url == "amqp://guest:guest@localhost:5672//"
    assert s.s3_endpoint == "http://localhost:3900"
    assert s.s3_access_key == "rag-dev-key"
    assert s.s3_secret_key == "rag-dev-secret-local"
    assert s.s3_region == "garage"
    assert s.s3_bucket == "rag-dev"
    assert s.parser_provider == "stub"
    assert s.embedding_provider == "stub"
    assert s.chunk_target_tokens == 600
    assert s.chunk_max_tokens == 1000
    assert s.chunk_overlap_tokens == 80
    assert s.embedding_batch_size == 64
    assert s.outbox_poll_interval_seconds == 1.0
    assert s.outbox_batch_size == 20
    assert s.max_upload_mb == 25


def test_broker_url_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """RAG_BROKER_URL selects the pytest vhost."""

    monkeypatch.setenv("RAG_BROKER_URL", "amqp://guest:guest@localhost:5672/rag_test")
    assert Settings(_env_file=None).broker_url == "amqp://guest:guest@localhost:5672/rag_test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `..\.venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: broker_url`.

- [ ] **Step 3: Implement the settings fields**

Add the fields from the Interfaces block to `Settings` (plain types; the provider factories in Task 4 validate the values).

- [ ] **Step 4: Add the dependencies and install**

`backend/pyproject.toml` dependencies: `celery>=5.6` (Python 3.14 support landed there; 5.5 stops at 3.13), `boto3`, `pgvector`, `python-multipart` (FastAPI refuses `UploadFile` routes without it), `pypdf`, `python-docx`. Dev extras: `celery-types`, `boto3-stubs[s3]` (strict mypy needs the stubs; if a package still fails, prefer a narrowly scoped mypy override).
Then run from the repo root: `.venv\Scripts\pip install -e "backend[dev]"`.

- [ ] **Step 5: Run the backend gates and commit the settings half**

Run: `ruff check .`; `ruff format --check .`; `mypy app tests`; `pytest`.
Expected: all green.

```bash
git add app/core/config.py pyproject.toml tests/test_config.py
git commit -m "feat(backend): add S3 pipeline settings and dependencies"
```

- [ ] **Step 6: Replace the MinIO compose service with Garage**

`deploy/docker-compose.yml`: remove the `minio` service, the `miniodata` volume, and the EOL TODO comment. Add service `garage`:
- `image: dxflrs/garage:v2.3.0` (pin the exact available tag; verify with `docker pull`).
- `command: /garage server --single-node --default-bucket` - the absolute path is required: the image is `FROM scratch` with no `PATH`, binary at `/garage`.
- `environment`: `GARAGE_DEFAULT_ACCESS_KEY=rag-dev-key`, `GARAGE_DEFAULT_SECRET_KEY=rag-dev-secret-local`, `GARAGE_DEFAULT_BUCKET=rag-dev` (key >= 8 chars of `[A-Za-z0-9._-]`, secret >= 16 printable ASCII; changing the secret after first start bricks the metadata volume - README task records the warning).
- `ports`: `3900:3900`, `3903:3903`; named volumes for metadata and data; mount `./garage.toml` at `/etc/garage/garage.toml`.

`deploy/garage.toml`: `replication_factor = 1`, metadata/data dirs on the named volumes, `[s3_api]` with `s3_region = "garage"` (must equal the settings default or Garage rejects the signature with `AuthorizationHeaderMalformed`) and `api_bind_addr = "0.0.0.0:3900"`, `[admin]` on 3903. Check the exact key names against the pinned image's docs/source.

- [ ] **Step 7: Verify compose and commit the deploy half**

Run: `docker compose -f deploy/docker-compose.yml up -d` then `docker compose -f deploy/docker-compose.yml ps`
Expected: `db`, `rabbitmq`, `garage` all up (garage finishes provisioning before its S3 listener starts, so no bootstrap step).

Remove the resolved MinIO item from `docs/backlog.md`.

```bash
git add deploy/docker-compose.yml deploy/garage.toml docs/backlog.md
git commit -m "chore(deploy): replace MinIO with Garage"
```

---

### Task 3: ORM models and the migration for the six new tables

**Files:**
- Create: `backend/app/sources/models.py` (`Source`, `SourceItem`), `backend/app/ingestion/models.py` (`Document`, `Chunk`, `IngestionRun`), `backend/app/outbox/models.py` (`OutboxEvent`)
- Create: `backend/alembic/versions/0005_ingestion_outbox.py`
- Modify: `backend/alembic/env.py` (import the three model modules), `backend/tests/test_alembic.py`

**Interfaces:**
- Consumes: `Base` from `app.core.models`.
- Produces: the six tables with spec 4.1 columns and constraints - `sources(type check 'upload')`; `source_items` with `unique(source_id, external_id)`; `documents` with `unique(source_item_id, content_hash)`; `chunks` with `unique(document_id, position)`, `chunk_type` check `'text'`, the Python attribute `chunk_metadata` mapped to the column named `metadata`, `embedding Vector(384)` (hardcoded literal, with a comment naming `STUB_EMBEDDING_DIM`), `search_vector` generated; `ingestion_runs` with the six-status check; `outbox_events` with the partial index. Models later tasks query: `Source.id/project_id/type/created_at`, `SourceItem.filename/external_id/content_hash/raw_object_key`, `IngestionRun.status/document_id/started_at/finished_at/error`, `Chunk.project_id/document_id/position/text/heading_path/chunk_metadata/content_hash/embedding`, `OutboxEvent.event_type/payload/published_at/attempts/last_error/created_at`.

- [ ] **Step 1: Write the failing schema tests**

In `tests/test_alembic.py`:

```python
def test_ingestion_tables_exist(*, engine: Engine) -> None:
    """Check that migrations created the six S3 tables."""

    with engine.connect() as conn:
        names = set(inspect(conn).get_table_names())
    assert {
        "sources", "source_items", "documents", "chunks", "ingestion_runs", "outbox_events",
    } <= names
```

Also: a new `test_vector_and_fulltext_indexes` that queries `pg_indexes` for `chunks` and asserts one definition contains `USING hnsw (embedding vector_cosine_ops)` and one contains `USING gin (search_vector)`; and that `outbox_events` has an index whose definition contains `published_at IS NULL`.

Fix `test_foreign_key_columns_are_indexed` to compare each index's **leading column only** (today it collects every column of every index, so dropping `ix_project_team_roles_team_id` would still pass), and grow `expected` with `"sources": {"project_id"}`, `"chunks": {"project_id"}`, `"ingestion_runs": {"document_id", "source_item_id"}` (the composite `(source_item_id, created_at)` serves the FK's leading column; the spec skips the uniques' leading columns).

Extend `test_migrations_downgrade_to_base`: assert `"vector" not in extensions` after the downgrade (mirroring the citext assertion).

- [ ] **Step 2: Run tests to verify they fail**

Run: `..\.venv\Scripts\python.exe -m pytest tests/test_alembic.py -v`
Expected: FAIL - tables and indexes missing.

- [ ] **Step 3: Implement the models**

House style: client-generated UUID pk, `DateTime(timezone=True)` with `func.now()` server defaults. JSONB from `sqlalchemy.dialects.postgresql`, `TSVECTOR` with `Computed("to_tsvector('english', text)", persisted=True)`, `Vector(384)` from `pgvector.sqlalchemy`. `chunks.project_id` carries the denormalization rationale comment (MD 27). Any relationship declared across these tables sets `passive_deletes=True` matching its `ondelete` (CASCADE or SET NULL), so a project delete stays one `DELETE` and the database cascades. `ingestion_runs.document_id` is `ON DELETE SET NULL`; every other FK cascades. Do not import provider modules from the models; the 384 literal carries a comment tying it to `STUB_EMBEDDING_DIM`.

- [ ] **Step 4: Implement migration 0005 and wire env.py**

Revision `0005`, down `0004`. `upgrade()`: `CREATE EXTENSION IF NOT EXISTS vector`; the six tables with all uniques/checks/FKs; FK indexes on `sources.project_id`, `chunks.project_id`, `ingestion_runs.document_id`, and the composite `ingestion_runs (source_item_id, created_at)`; the outbox partial index on `created_at WHERE published_at IS NULL`; HNSW via `op.create_index(..., postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"})` and GIN via `postgresql_using="gin"`. The embedding column is the literal `Vector(384)` - a migration never reads a runtime value. `downgrade()` reverses everything and drops the extension. Add the three model imports to `alembic/env.py` beside the existing ones.

- [ ] **Step 5: Run tests to verify they pass**

Run: `..\.venv\Scripts\python.exe -m pytest tests/test_alembic.py -v`
Expected: PASS, including the fixed leading-column test and the vector downgrade assertion.

- [ ] **Step 6: Full backend verification and commit**

Run: all four backend gates. Expected: green.

```bash
git add app/sources/models.py app/ingestion/models.py app/outbox/models.py alembic/versions/0005_ingestion_outbox.py alembic/env.py tests/test_alembic.py
git commit -m "feat(backend): add ingestion and outbox schema"
```

---

### Task 4: Provider interfaces and stub implementations

**Files:**
- Create: `backend/app/providers/__init__.py`, `backend/app/providers/base.py`, `backend/app/providers/stub_parser.py`, `backend/app/providers/stub_embeddings.py`
- Create: `backend/tests/fixtures/make_tiny_pdf.py`, `backend/tests/fixtures/tiny.pdf` (generated once, committed)
- Test: `backend/tests/providers/__init__.py`, `backend/tests/providers/test_stub_parser.py`, `backend/tests/providers/test_stub_embeddings.py`

**Interfaces:**
- Consumes: `Settings`.
- Produces (Task 5/8 consume exactly these):
  - `NormalizedElement` dataclass: `type: str` (`"heading"` | `"paragraph"`), `text: str`, `level: int | None = None`.
  - `NormalizedDocument` dataclass: `title: str`, `elements: list[NormalizedElement]`, `metadata: dict[str, str]`.
  - `ParseError(Exception)` - raised when a parser cannot extract a usable document.
  - `Parser` protocol: `parse(*, filename: str, content: bytes) -> NormalizedDocument`.
  - `EmbeddingProvider` protocol: `dimension: int`, `embed_documents(*, texts: list[str]) -> list[list[float]]`, `embed_query(*, text: str) -> list[float]`.
  - `get_parser(*, settings: Settings) -> Parser` and `get_embedding_provider(*, settings: Settings) -> EmbeddingProvider`; unknown provider value raises `ValueError`.
  - `StubParser` (PDF: one paragraph element per non-empty page via pypdf, empty `heading_path`; DOCX: `Heading N` style -> heading level N, other non-empty paragraphs -> paragraph elements, tables skipped; title from the filename stem; `metadata == {"filename": filename}`; zero extractable elements raises `ParseError`).
  - `STUB_EMBEDDING_DIM = 384` and `StubEmbeddingProvider` (deterministic hash-bag: lowercase whitespace split, per-token sha256 -> bucket + sign bit, L2-normalized; empty text -> zero vector). `STUB_EMBEDDING_DIM` carries the inline comment: changing it requires an Alembic migration re-typing `chunks.embedding` **and** re-embedding every stored chunk (backlog 2026-10-12; re-embedding runs from `chunks.text`, no re-parse).

- [ ] **Step 1: Create the tiny PDF fixture**

`tests/fixtures/make_tiny_pdf.py`: a script (module docstring; `main()` with docstring) writing a minimal single-page PDF to `tests/fixtures/tiny.pdf` - catalog/pages/page/contents/font objects, content stream `BT /F1 12 Tf 72 720 Td (Stub fixture paragraph.) Tj ET`, xref offsets computed by accumulating byte positions (pypdf is forgiving, but compute them properly). Run it once with the venv python; commit script and `tiny.pdf` together. Task 12 uploads this same file through the browser.

- [ ] **Step 2: Write the failing tests**

`test_stub_parser.py`:
- `test_pdf_fixture_yields_one_paragraph_per_page`: parse `tiny.pdf` -> one paragraph element whose text contains `Stub fixture paragraph.`, title `tiny`, `metadata == {"filename": "tiny.pdf"}`.
- `test_docx_headings_and_paragraphs`: build a docx in-test with python-docx (`Heading 1`, `Heading 2`, paragraphs, plus a table row) -> element types/levels match, table contributes nothing.
- `test_empty_document_raises_parse_error`: empty bytes named `x.pdf` -> `ParseError`.
- `test_unknown_parser_provider_raises`: `get_parser` with `parser_provider="nope"` -> `ValueError`.

`test_stub_embeddings.py`:
- `test_embedding_is_deterministic`: same text twice -> equal vectors; different texts -> different.
- `test_dimension_matches_constant`: `len(vector) == STUB_EMBEDDING_DIM == 384` and `provider.dimension == 384`.
- `test_l2_normalized`: `sum(v * v)` is 1 within 1e-6 for non-empty text.
- `test_empty_text_yields_zero_vector`.

- [ ] **Step 3: Run tests to verify they fail**

Run: `..\.venv\Scripts\python.exe -m pytest tests/providers -v`
Expected: FAIL (modules missing).

- [ ] **Step 4: Implement**

Per the Interfaces block; providers are selected by string and never imported by the models.

- [ ] **Step 5: Run tests to verify they pass, then gates**

Run: `..\.venv\Scripts\python.exe -m pytest tests/providers -v`, then all four backend gates.
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add app/providers tests/providers tests/fixtures
git commit -m "feat(backend): add stub parser and embedding providers"
```

---

### Task 5: Structure-aware chunker

**Files:**
- Create: `backend/app/ingestion/chunking.py`
- Test: `backend/tests/ingestion/__init__.py`, `backend/tests/ingestion/test_chunking.py`

**Interfaces:**
- Consumes: `NormalizedElement` (Task 4).
- Produces: `ChunkText` dataclass with `text: str` and `heading_path: list[str]`; `chunk_elements(*, elements: list[NormalizedElement], target_tokens: int, max_tokens: int, overlap_tokens: int) -> list[ChunkText]`. Raises `ValueError` on an empty element list; returns `[]` for a headings-only document (the service turns that into a parse error). Token estimate is `ceil(words * 4 / 3)`, a documented estimate, no tokenizer. Invariant: no emitted chunk's estimate ever exceeds `max_tokens`.

- [ ] **Step 1: Write the failing golden tests**

Use small budgets (e.g. target 20, max 40, overlap 8) with word-counted fixtures:
- `test_heading_boundaries_start_new_chunks` - a pack never spans a heading.
- `test_packing_stops_at_target` - the overflowing element starts the next chunk instead of enlarging the current one.
- `test_oversize_element_hard_splits_with_overlap` - a single over-max element splits into windows that each stay under max, consecutive windows share overlap-sized word prefixes.
- `test_heading_path_records_the_stack` - level-1 then level-2 headings give `["h1"]` then `["h1", "h2"]`.
- `test_tiny_document_yields_one_chunk`.
- `test_headings_only_document_yields_zero_chunks`.
- `test_empty_element_list_raises`.
- `test_heading_text_not_duplicated_into_chunk_text`.
- `test_no_chunk_exceeds_max_tokens` - re-asserted across every fixture's output.

- [ ] **Step 2: Run tests to verify they fail**

Run: `..\.venv\Scripts\python.exe -m pytest tests/ingestion/test_chunking.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Walk the elements with a heading stack (`stack[:level - 1] + [text]`, missing level treated as 1). Pack consecutive paragraphs until adding the next would exceed `chunk_target_tokens`; a single element over `chunk_max_tokens` hard-splits by words into windows of `floor(max_tokens * 3 / 4)` words stepping back `overlap`-sized windows, which keeps every window's estimate at or under max. Heading text is recorded only in `heading_path`.

- [ ] **Step 4: Run tests to verify they pass, then gates and commit**

Run: `..\.venv\Scripts\python.exe -m pytest tests/ingestion/test_chunking.py -v`, then the four backend gates. Expected: green.

```bash
git add app/ingestion/chunking.py tests/ingestion
git commit -m "feat(backend): add structure-aware chunker"
```

---

### Task 6: Garage storage service

**Files:**
- Create: `backend/app/storage/__init__.py`, `backend/app/storage/service.py`
- Test: `backend/tests/storage/__init__.py`, `backend/tests/storage/test_service.py`

**Interfaces:**
- Consumes: `Settings` (S3 block).
- Produces: `build_raw_object_key(*, project_id: UUID, source_item_id: UUID, content_hash: str, filename: str) -> str` returning `raw/{project_id}/{source_item_id}/{content_hash}/{filename}`; `StorageService(*, settings: Settings)` with `put_object(*, key: str, content: bytes, content_type: str | None = None) -> None` and `get_object(*, key: str) -> bytes`; `StorageUnavailableError(Exception)`. boto3 client with `endpoint_url`/credentials/`region_name` from settings and path-style addressing (`Config(s3={"addressing_style": "path"})`); client errors and connection failures wrap into `StorageUnavailableError`.

- [ ] **Step 1: Write the failing tests**

- `test_object_key_format`: fixed UUIDs, hash, and filename -> the exact key string.
- `test_put_get_roundtrip`: against the compose Garage, put bytes under a UUID-carrying key, get them back.
- `test_get_missing_key_raises`: missing key -> `StorageUnavailableError`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `..\.venv\Scripts\python.exe -m pytest tests/storage -v` (Garage up).
Expected: FAIL (module missing).

- [ ] **Step 3: Implement, run green, gates, commit**

Run: `..\.venv\Scripts\python.exe -m pytest tests/storage -v`, then the four backend gates. Expected: green.

```bash
git add app/storage tests/storage
git commit -m "feat(backend): add Garage storage service"
```

---

### Task 7: Outbox event types, payloads, and routing

**Files:**
- Create: `backend/app/outbox/__init__.py`, `backend/app/outbox/events.py` (`models.py` exists from Task 3)
- Test: `backend/tests/outbox/__init__.py`, `backend/tests/outbox/test_events.py`

**Interfaces:**
- Consumes: `OutboxEvent`, `Session`.
- Produces (the API process imports only this from the outbox - no Celery anywhere in it):
  - Constants: `SOURCE_ITEM_INGESTION_REQUESTED = "source_item_ingestion_requested"`, `DOCUMENT_READY_FOR_EMBEDDING = "document_ready_for_embedding"`, `INGESTION_QUEUE = "ingestion"`, `EMBED_QUEUE = "embed"` (queue names live here, not in the workers module).
  - `EVENT_ROUTES: Mapping[str, tuple[str, str]]` = `{SOURCE_ITEM_INGESTION_REQUESTED: ("ingest_source_item", INGESTION_QUEUE), DOCUMENT_READY_FOR_EMBEDDING: ("embed_document", EMBED_QUEUE)}`.
  - `enqueue_source_item_ingestion_requested(*, db: Session, source_item_id: UUID, ingestion_run_id: UUID, raw_object_key: str, content_hash: str) -> OutboxEvent` - payload values stored as JSON strings (`str(source_item_id)` etc.), `aggregate_type="source_item"`, `aggregate_id=source_item_id`.
  - `enqueue_document_ready_for_embedding(*, db: Session, document_id: UUID, ingestion_run_id: UUID) -> OutboxEvent` - `aggregate_type="document"`, `aggregate_id=document_id`.

- [ ] **Step 1: Write the failing tests**

- `test_ingestion_requested_event_row`: enqueue -> row fields + payload exactly `{"source_item_id": <str>, "ingestion_run_id": <str>, "raw_object_key": ..., "content_hash": ...}`, `published_at is None`, `attempts == 0`.
- `test_document_ready_event_row`: payload exactly `{"document_id": <str>, "ingestion_run_id": <str>}`.
- `test_routes_cover_both_events`: `EVENT_ROUTES` equals the two expected pairs.

- [ ] **Step 2: Run tests to verify they fail**

Run: `..\.venv\Scripts\python.exe -m pytest tests/outbox -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement, run green, gates, commit**

Run: `..\.venv\Scripts\python.exe -m pytest tests/outbox -v`, then the four backend gates. Expected: green.

```bash
git add app/outbox/events.py tests/outbox
git commit -m "feat(backend): add outbox event types and routing"
```

---

### Task 8: Ingestion and embed pipeline services plus the dimension guard

**Files:**
- Create: `backend/app/ingestion/service.py`
- Test: `backend/tests/ingestion/test_service.py`

**Interfaces:**
- Consumes: models (Task 3), `chunk_elements` (Task 5), `StorageService` (Task 6), parser/embedding providers and `get_*` factories (Task 4), outbox enqueue helpers (Task 7).
- Produces (Task 9/10 consume exactly these):
  - `ingest_source_item(*, db: Session, source_item_id: UUID, ingestion_run_id: UUID, raw_object_key: str, content_hash: str, storage: StorageService, parser: Parser, settings: Settings) -> None`
  - `embed_document(*, db: Session, document_id: UUID, ingestion_run_id: UUID, embedding_provider: EmbeddingProvider, settings: Settings) -> None`
  - `canonical_document_json(*, document: NormalizedDocument) -> str` - `json.dumps` of title + elements + metadata only (never ids or timestamps), `sort_keys=True`, compact separators.
  - `query_embedding_dimension(*, db: Session) -> int | None` - `format_type` over `pg_attribute` for `chunks.embedding`, parsed from `vector(N)`; `None` when absent.
  - `verify_embedding_dimension(*, expected_dimension: int, actual_dimension: int | None) -> None` - raises `RuntimeError` shaped like: `chunks.embedding is vector(384) but the selected provider emits 512; changing the dimension requires an Alembic migration`.
  - `run_startup_checks(*, db: Session, embedding_provider: EmbeddingProvider) -> None` - query + verify.

- [ ] **Step 1: Write the failing tests**

Fixtures build the identity/project/source/item rows directly on `db_session`, put bytes into Garage through the real `StorageService`, and seed a `queued` run. Use an in-test generated docx (heading + paragraphs) as the good document.

- `test_ingest_end_to_end`: after the call, the run is `indexing` with `document_id` linked and `started_at` set; the document row carries the canonical hash, `normalized_content`, and the `raw_object_key` copied from the item; chunk rows exist with `chunk_type == "text"`, `heading_path`, `chunk_metadata == {"filename": ...}`, `content_hash`, `embedding is None`, and each row's stored `search_vector` equals `to_tsvector('english', text)` (compare in SQL); a `document_ready_for_embedding` outbox row exists with the full payload.
- `test_duplicate_delivery_no_ops`: a second call returns without touching the run or creating a second document.
- `test_missing_run_no_ops`: random ids -> no exception, no rows.
- `test_garbage_pdf_fails_the_run`: garbage bytes named `.pdf` -> run `failed` with `error` text, `finished_at` set, no document.
- `test_zero_chunk_document_fails_the_run`: a headings-only docx -> run `failed` with a clear "no text content" message.
- `test_identical_version_conflict_is_idempotent_noop`: two queued runs on one item; ingest both -> the second run ends `ready` pointing at the first document, with still exactly one document and one chunk set (MD 19 no-op; unreachable in S3, the constraint is the backstop).
- `test_embed_updates_vectors_and_marks_ready`: after ingest, embed -> every chunk embedding non-null (384 floats), run `ready` with `finished_at`.
- `test_embed_is_idempotent_on_redelivery`: embed twice -> no error, run stays `ready`, vectors identical.
- `test_embed_batches_chunks`: a counting `EmbeddingProvider` wrapper around the stub records call sizes; five chunks with `embedding_batch_size=2` -> sizes `[2, 2, 1]`.
- `test_embed_missing_document_no_ops`: random `document_id` -> no exception.
- `test_dimension_guard`: `query_embedding_dimension` on the test database -> 384; `verify_embedding_dimension(expected_dimension=384, actual_dimension=384)` passes; with `expected_dimension=512` and `actual_dimension=384` raises `RuntimeError` naming both numbers and the migration; with `actual_dimension=None` raises.

- [ ] **Step 2: Run tests to verify they fail**

Run: `..\.venv\Scripts\python.exe -m pytest tests/ingestion/test_service.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

`ingest_source_item`: claim with `UPDATE ... SET status='fetching', started_at=now() WHERE id=:run_id AND status='queued'` (zero rows -> duplicate or stale delivery -> return); commit; fetch the item row (missing subject rows are impossible under the FK - the claim already absorbed them); load bytes via `storage.get_object` using the **payload's** `raw_object_key`, never a rebuilt key; any storage/provider error -> conditional `failed` against `expected='fetching'`, commit, return. Transition `processing` (conditional, committed) so the parse runs with no open transaction. Parse -> zero elements or zero chunks -> `failed` (expected `'processing'`). Hash via `canonical_document_json`, chunk via `chunk_elements` with the three settings budgets, then **one transaction**: document + chunks (positions from enumeration, `project_id` via the item's source) + `enqueue_document_ready_for_embedding` + run -> `indexing` (conditional) -> commit. An `IntegrityError` on the document insert rolls back and marks the run `ready` against the existing document (spec 5.3 backstop). Other errors -> `failed` with the error text. The service never re-raises; the run row is the outcome record.

`embed_document`: load document + chunks (missing document -> return); commit so `embed_documents` runs outside any transaction; per batch: embed, then `UPDATE chunks.embedding` in place, commit per batch; then conditional `ready` with `finished_at` (`WHERE status='indexing'`); errors -> `failed` (expected `'indexing'`). In-place updates plus the deterministic stub make re-delivery naturally idempotent.

- [ ] **Step 4: Run tests to verify they pass, then gates and commit**

Run: `..\.venv\Scripts\python.exe -m pytest tests/ingestion -v`, then the four backend gates. Expected: green.

```bash
git add app/ingestion/service.py tests/ingestion/test_service.py
git commit -m "feat(backend): add ingestion and embed pipeline services"
```

---

### Task 9: Upload and sources endpoints

**Files:**
- Create: `backend/app/sources/__init__.py`, `backend/app/sources/router.py`, `backend/app/sources/schemas.py`, `backend/app/sources/service.py`
- Modify: `backend/app/main.py` (include the router)
- Test: `backend/tests/sources/__init__.py`, `backend/tests/sources/test_sanitize.py`, `backend/tests/sources/test_api.py`

**Interfaces:**
- Consumes: `get_project_for_user_with_role`, `get_project_visible_to_user` (projects service), models, `StorageService`, `StorageUnavailableError`, enqueue helper, `session_scope`-free request session.
- Produces:
  - `sanitize_filename(*, filename: str) -> str` - last segment after splitting on `/` and `\`, control characters dropped, empty result or length > 255 -> `ValueError`.
  - `create_upload_source(*, db: Session, project: Project, filename: str, content_type: str | None, content: bytes, storage: StorageService, settings: Settings) -> Source` - sha256 raw bytes -> `content_hash`; pre-generate the item id and build the key; copy needed ids into locals, **`db.commit()`** (ends the read transaction; commit, not rollback - the test harness savepoint makes rollback discard setup rows and re-opening a transaction on instance access would leave one open across the PUT); PUT the object; then one transaction: source + item + `queued` run + outbox row -> commit.
  - `SourceListItem` dataclass: `source: Source`, `filename: str`, `status: str`.
  - `list_sources(*, db: Session, project_id: UUID) -> list[SourceListItem]` - newest first, lateral/subquery join of each source's single item to its latest run by `created_at`, `filename`/`status` derived (NULL status coalesced to `"queued"`, defensive; no ties in production since one run commits per transaction).
  - Routes: `POST /projects/{project_id}/sources` (editor role; 201 `SourceOut`; 422 validation; 503 storage; 404 house convention; multipart field name `file`; `file: Annotated[UploadFile, File()]`) and `GET /projects/{project_id}/sources` (visible-to-user; newest first; no pagination).
  - `SourceOut`: `id, project_id, type, status, filename, created_at`.

- [ ] **Step 1: Write the failing sanitize unit tests**

`test_sanitize.py`: `"notes.pdf" -> "notes.pdf"`; `"../evil/report.pdf" -> "report.pdf"`; backslash variant; `"dir\\x.pdf"` control characters dropped; name over 255 chars and empty basename -> `ValueError`.

- [ ] **Step 2: Write the failing API tests**

`test_api.py` (TestClient, real Garage):
- `test_upload_creates_source_item_run_and_event`: 201; body equals `SourceOut` shape with `status == "queued"`; source + item (identity, `raw_object_key`, hash) + `queued` run + outbox row with the full four-key payload all exist; `StorageService.get_object` returns the uploaded bytes.
- `test_storage_put_runs_with_no_open_transaction`: monkeypatch the `StorageService` symbol where the router constructs it (`app.sources.router.StorageService`, since `create_upload_source` receives the client as a parameter) with a subclass that records `db.in_transaction()` during `put_object` before calling the real one; assert it recorded `[False]`.
- `test_upload_validates_extension_empty_and_size`: `.txt` -> 422 friendly detail; empty file -> 422; a 26MB `.pdf` body -> 422 with the size message (checked via `UploadFile.size` before reading the bytes).
- `test_upload_filename_sanitized`: multipart filename `"../evil/report.pdf"` -> 201 with stored filename `"report.pdf"`; a filename sanitizing to empty -> 422.
- `test_upload_requires_editor_role`: a second user holding only a viewer `ProjectTeamRole` (seeded via ORM) -> upload 404, list 200; a stranger -> 404.
- `test_public_project_viewer_can_list_but_not_upload`: project made public; stranger `GET` 200 / `POST` 404.
- `test_sources_list_derives_status_and_filename`: upload, move the run to `processing` via ORM, GET -> derived `processing` and the item filename; seed a second source with an explicit earlier `created_at` and assert newest-first ordering.
- `test_project_delete_cascades_fully_ingested_source`: upload, run `ingest_source_item` + `embed_document` through the services, `DELETE /projects/{id}` -> 204; every row gone across sources, source_items, documents, chunks, ingestion_runs. (Outbox rows for deleted aggregates linger by design - no FK - and later task no-ops absorb them.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `..\.venv\Scripts\python.exe -m pytest tests/sources -v`
Expected: FAIL (modules missing).

- [ ] **Step 4: Implement**

Router: role/visibility lookups -> 404 `"project not found"`; validation before reading the body (extension `.pdf`/`.docx`, non-empty, `size <= max_upload_mb * 1024 * 1024`), friendly 422 details; `file.file.read()`; `StorageUnavailableError` -> `HTTPException(503, "Could not store the file. Please try again.")`. Service per the Interfaces block. `main.py` includes the router. HTTP concerns stay in the router; row creation + listing live in the service.

- [ ] **Step 5: Run tests to verify they pass, then gates and commit**

Run: `..\.venv\Scripts\python.exe -m pytest tests/sources -v`, then the four backend gates. Expected: green.

```bash
git add app/sources app/main.py tests/sources
git commit -m "feat(backend): add upload and sources endpoints"
```

---

### Task 10: Celery worker, dispatcher, and broker test plumbing

**Files:**
- Create: `backend/app/workers/__init__.py`, `backend/app/workers/celery_app.py`, `backend/app/workers/tasks.py`, `backend/app/workers/dispatcher.py`
- Modify: `backend/app/core/db.py` (add `session_scope`)
- Create: `backend/scripts/broker_admin.py`
- Modify: `backend/tests/conftest.py` (session-scoped `broker_url` fixture)
- Test: `backend/tests/workers/__init__.py`, `backend/tests/workers/test_celery_app.py`, `backend/tests/workers/test_dispatcher_integration.py`

**Interfaces:**
- Consumes: services (Task 8), events (Task 7), `SessionLocal`.
- Produces:
  - `session_scope()` context manager in `app/core/db.py`: yield a session, commit on success, rollback on error, close always.
  - `make_celery_app(*, broker_url: str) -> Celery` in `app/workers/celery_app.py` - broker twin of `make_engine`; `task_acks_late=True`, `broker_transport_options={"confirm_publish": True}` (publisher confirms are a real wait), no result backend, `include=["app.workers.tasks"]`; module-level `celery_app = make_celery_app(broker_url=get_settings().broker_url)` points at the dev vhost exactly as `SessionLocal` points at the dev database.
  - Worker startup: a `worker_init` signal handler running `run_startup_checks` and raising `SystemExit` (not `Exception`, which Celery's signal dispatch catches and swallows); a `worker_ready` handler logging `celery worker ready` at WARNING to stderr.
  - Tasks: `ingest_source_item(*, source_item_id: str, ingestion_run_id: str, raw_object_key: str, content_hash: str)` and `embed_document(*, document_id: str, ingestion_run_id: str)` - parameter names equal the payload keys; each opens `session_scope`, converts ids to `UUID`, selects the stub providers via settings, and calls the Task 8 service function.
  - `dispatch_batch(*, db: Session, app: Celery, batch_size: int) -> int` in `app/workers/dispatcher.py`: one short transaction - select unpublished rows ordered by `created_at` with `FOR UPDATE SKIP LOCKED`, publish each via the injected app's `send_task` routed through `EVENT_ROUTES`, set `published_at` only after the (confirmed) publish; a missing route bumps `attempts`/`last_error` and continues; a publish exception bumps the row and **ends the batch**; commit; return the published count. `main()` builds the app from settings, prints `dispatcher ready` to stderr (flushed), and loops `dispatch_batch` + `sleep(outbox_poll_interval_seconds)` holding nothing across the sleep.
  - `ensure_broker_vhost(*, broker_url: str, management_url: str = "http://localhost:15672") -> None` in `backend/scripts/broker_admin.py`: `PUT /api/vhosts/{vhost}` then `PUT /api/permissions/{vhost}/guest` with `{"configure": ".*", "write": ".*", "read": ".*"}` (a new vhost grants no permissions by default), both idempotent, credentials parsed from `broker_url`.
  - Conftest: session-scoped `broker_url` fixture returning `os.environ.get("RAG_TEST_BROKER_URL", "amqp://guest:guest@localhost:5672/rag_test")` after ensuring the vhost.

- [ ] **Step 1: Write the failing tests**

`test_celery_app.py`:
- `test_make_celery_app_configures_broker_and_acks`: `broker_url`, `task_acks_late`, `broker_transport_options["confirm_publish"]` set as above; no result backend.
- `test_worker_init_refuses_on_dimension_mismatch`: the handler body with a fake provider (`dimension = 512`) against the test database -> raises `SystemExit` whose message names both numbers and the Alembic migration.
- `test_worker_init_passes_with_stub`: real stub provider against the test database -> no exception.

`test_dispatcher_integration.py` (real RabbitMQ on the `rag_test` vhost; a module fixture purges the `ingestion` and `embed` queues before seeding - declare via kombu then purge, so leftover messages from failed runs never leak into a later test):
- `test_dispatch_publishes_and_marks`: seed an ingestion event row; `dispatch_batch(db, app=make_celery_app(broker_url=broker_url), batch_size=20)` -> `published_at` set; drain the `ingestion` queue with a plain kombu `SimpleQueue` -> the message's task name is `ingest_source_item` and its `kwargs` equal the row payload.
- `test_dispatch_routes_embed_events_to_embed_queue`: a `document_ready_for_embedding` row lands on the `embed` queue.
- `test_publish_failure_bumps_and_retries`: monkeypatch the app's `send_task` to raise -> `attempts == 1`, `last_error` set, `published_at` None; un-patch, dispatch again -> published, message drained.
- `test_missing_route_bumps_without_breaking`: one row with an unknown `event_type` and one valid row in the same batch -> the unknown row is bumped, the valid row still published.

- [ ] **Step 2: Run tests to verify they fail**

Run: `..\.venv\Scripts\python.exe -m pytest tests/workers -v` (RabbitMQ up).
Expected: FAIL (modules missing).

- [ ] **Step 3: Implement**

Per the Interfaces block. The tasks are registered on the module-level app; the dispatcher takes its app as a keyword-only argument, so tests point it at the `rag_test` vhost instead of the dev default.

- [ ] **Step 4: Run tests to verify they pass, then gates and commit**

Run: `..\.venv\Scripts\python.exe -m pytest tests/workers -v`, then the four backend gates. Expected: green.

```bash
git add app/workers app/core/db.py scripts/broker_admin.py tests/conftest.py tests/workers
git commit -m "feat(backend): add Celery worker and outbox dispatcher"
```

---

### Task 11: Project page with upload and status polling

**Files:**
- Modify: `web/src/app/api.ts` (`tagTypes` gains `"Source"`), `web/src/app/AppRoutes.tsx` (guarded `/projects/:projectId` route), `web/src/features/projects/projectsApi.ts` (add `getProject`), `web/src/features/projects/ProjectsPage.tsx` (project names become links), `web/src/test/handlers.ts`
- Create: `web/src/features/sources/sourcesApi.ts`, `web/src/features/projects/ProjectPage.tsx`
- Test: `web/src/features/projects/ProjectPage.test.tsx`, `web/src/features/projects/ProjectsPage.test.tsx` (extend), `web/src/app/App.test.tsx` (extend)

**Interfaces:**
- Consumes: the S3 API contract - `POST /projects/{id}/sources` (multipart field `file`) -> 201 `SourceOut`; `GET /projects/{id}/sources` -> `SourceOut[]`; `GET /projects/{id}` (S1).
- Produces:
  - `sourcesApi`: `type Source = { id, project_id, type, status: "queued" | "fetching" | "processing" | "indexing" | "ready" | "failed", filename, created_at }`; `getSources: build.query<Source[], string>` with `providesTags: ["Source"]`; `uploadSource: build.mutation<Source, { projectId: string; file: File }>` building `FormData` with field `file`, `invalidatesTags: ["Source"]`.
  - `getProject: build.query<Project, string>` in `projectsApi`.
  - `ProjectPage` at `/projects/:projectId` (inside `RequireAuth`, `DashboardLayout`): header with the project name plus a back link to `/projects`; upload card with a hidden `input[type=file]` (`accept=".pdf,.docx"`), client-side extension and 25MB size checks mirroring the server copy, `Upload` disabled while the mutation is pending, inline `role="alert"` errors (client rejections and `getErrorMessage` for 422/503); sources table (filename, status chip, created date); chip mapping: the four in-flight statuses -> blue/primary style, `ready` -> green `success`, `failed` -> red `error`, labels are the capitalized status (the e2e asserts a `Ready` chip); polling via `pollingInterval: 2000` while any row is non-terminal, `0` once all rows are terminal (`0` disables polling in the installed RTK Query types; `false` fails the build); project 404 -> friendly `Project not found.` state with the back link.

- [ ] **Step 1: Write the failing tests**

MSW handlers gain: `GET */projects/p-1` -> project fixture; `GET */projects/p-1/sources` -> three sources (`queued`, `ready`, `failed`); `POST */projects/p-1/sources` -> 201 source fixture.

`ProjectPage.test.tsx`:
- renders the project header, back link, upload card, and table rows with the blue/green/red chips;
- upload posts multipart `FormData` with a `file` part (assert via the request's content-type and `request.formData()`);
- `Upload` disabled while the POST is pending (deferred handler);
- client rejections: a `.txt` file and a >25MB `File` show friendly copy and never post;
- server 422 (array detail) and 503 (string detail) show friendly copy in a `role="alert"` element;
- polling: with a non-terminal row, fake-timer advances keep firing `GET /sources`; with all-terminal rows, no further requests;
- `GET /projects/p-1` 404 -> `Project not found.` plus back link.

`ProjectsPage.test.tsx`: project names are links with `href` `/projects/{id}`. `App.test.tsx`: an authenticated visit to `/projects/p-1` renders the project page.

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- ProjectPage ProjectsPage App`
Expected: FAIL (modules missing / assertions fail).

- [ ] **Step 3: Implement**

Per the Interfaces block; Devias styling continuity (S2 spec section 4); pages never build URLs or parse response bodies - everything goes through `sourcesApi`/`projectsApi`.

- [ ] **Step 4: Run the web gates and commit**

Run: `npm run lint`; `npm run format:check`; `npm test`; `npm run build`.
Expected: all green.

```bash
git add -A src
git commit -m "feat(web): add project page with upload and status polling"
```

---

### Task 12: Full-pipeline Playwright journey

**Files:**
- Modify: `backend/scripts/e2e_db.py` (bootstrap creates the `rag_e2e` vhost; truncate grows the six tables), `web/playwright.config.ts` (webServer entries), `web/e2e/journey.spec.ts` (new upload journey)
- Create: `backend/scripts/make_sample_docx.py`

**Interfaces:**
- Consumes: everything from Tasks 3-11; `ensure_broker_vhost`; the committed `backend/tests/fixtures/tiny.pdf`.
- Produces: a passing `npm run e2e` proving the spec's done-when: upload from the browser through the real worker + dispatcher to `ready`, both stub parsers, one broker path.

- [ ] **Step 1: Extend e2e_db.py and add the docx generator**

`bootstrap()`: after creating the database, `ensure_broker_vhost(broker_url="amqp://guest:guest@localhost:5672/rag_e2e")` (import from `scripts.broker_admin`; the sys.path insert already precedes app imports). `truncate()`: add `sources, source_items, documents, chunks, ingestion_runs, outbox_events` to the `TRUNCATE ... CASCADE` list.

`backend/scripts/make_sample_docx.py`: writes a docx with one `Heading 1` (`Sample heading`) and one paragraph to the path given as `argv[1]` (module docstring; `main()` with docstring - the same docstring rules as the rest of `scripts`).

- [ ] **Step 2: Extend the Playwright config**

Keep the existing uvicorn entry first (its command runs `e2e_db.py bootstrap`, which now also creates the vhost - the array order is load-bearing: Playwright 1.64 starts entries one at a time, waiting for each). Add, in order, before the Vite entry:

```ts
{
  // No ready URL exists, so the entries wait on stderr lines; Celery logs to
  // stderr and worker_redirect_stdouts sends print() output there too.
  command: `"${PYTHON}" -m celery -A app.workers.celery_app worker --pool=solo -Q ingestion,embed`,
  cwd: "../backend",
  env: {
    RAG_DATABASE_URL: "postgresql+psycopg://rag:rag@localhost:5432/rag_e2e",
    RAG_BROKER_URL: "amqp://guest:guest@localhost:5672/rag_e2e",
  },
  wait: { stderr: /celery worker ready/ },
  timeout: 120_000,
},
{
  command: `"${PYTHON}" -m app.workers.dispatcher`,
  cwd: "../backend",
  env: {
    RAG_DATABASE_URL: "postgresql+psycopg://rag:rag@localhost:5432/rag_e2e",
    RAG_BROKER_URL: "amqp://guest:guest@localhost:5672/rag_e2e",
  },
  wait: { stderr: /dispatcher ready/ },
  timeout: 60_000,
},
```

- [ ] **Step 3: Write the upload journey**

In `journey.spec.ts`, alongside the existing test: generate `sample.docx` in a fresh temp dir via `execFileAsync(PYTHON, ["scripts/make_sample_docx.py", docxPath], { cwd: "../backend" })`; register; open the `Default` project by clicking its row link; `setInputFiles` the hidden file input with the tiny PDF, `Upload`, then the same for the docx; then assert both files reach `ready`:

```ts
// The default 5s expect timeout does not cover the full pipeline, so the
// assertion carries an explicit one inside the 30s test budget.
await expect(page.getByRole("cell", { name: "Ready" })).toHaveCount(2, { timeout: 20_000 });
```

The two Ready chips are one assertion, so the whole wait fits the 30s budget even in the worst case.

- [ ] **Step 4: Run the suite and debug real findings**

Run: `npm run e2e` (compose services up).
Expected: PASS for both journeys. A failure is a real finding - use `superpowers:systematic-debugging`; never relax the spec. Stale queue messages after truncation are absorbed by the ack-and-skip guards; already-uploaded Garage objects are orphaned harmlessly.

- [ ] **Step 5: Commit**

```bash
git add ../backend/scripts/e2e_db.py ../backend/scripts/make_sample_docx.py playwright.config.ts e2e/journey.spec.ts
git commit -m "test(e2e): prove the full pipeline through the browser"
```

---

### Task 13: Runbook, spec statuses, and final verification

**Files:**
- Modify: `README.md`, `../specs/2026-10-06-roadmap.md`, `docs/superpowers/specs/2026-10-12-s3-upload-ingestion-design.md`, `docs/backlog.md`

**Interfaces:**
- Consumes: a green Task 12.
- Produces: documentation matching the shipped slice; both spec statuses flipped; every remaining follow-up backlog-tracked.

- [ ] **Step 1: Update the README backend runbook**

- Prerequisites/services: Garage replaces MinIO - S3 API on `localhost:3900`, admin on `3903`, fixed dev credentials `rag-dev-key` / `rag-dev-secret-local`, bucket `rag-dev`; include the warning that changing `GARAGE_DEFAULT_SECRET_KEY` after first start bricks the metadata volume until it is wiped.
- Add the three dev commands from spec section 3.5 after "Run the API": `celery -A app.workers.celery_app worker --pool=solo -Q ingestion,embed` and `python -m app.workers.dispatcher` (both from `backend/` with the venv), noting `--pool=solo` is the supported Windows pool.
- Test prerequisites: db + RabbitMQ + Garage; the `rag_test` broker vhost is created by the suite itself.
- Only add what S3 introduces; the README-lacks-web-instructions backlog item stays untouched.

- [ ] **Step 2: Flip the spec statuses**

- `2026-10-12-s3-upload-ingestion-design.md`: Status -> `Implemented on master (S3).`
- Slices spec: S3 roadmap row -> `✅ done`; the section 7 next-step line's remaining MinIO mention flips to Garage. Leave the S7 row's "Celery Beat sync polling" wording as-is - decision 3 deliberately leaves S7's scheduler open.

- [ ] **Step 3: Backlog hygiene**

Verify the re-embedding follow-up and stuck-run recovery entries remain recorded (they do, 2026-10-12); add anything the execution surfaced as timestamped entries with commit links per AGENTS.md.

- [ ] **Step 4: Final whole-system verification**

Run, from `backend/`: `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest`.
Run, from `web/`: `npm run lint`, `npm run format:check`, `npm run test`, `npm run build`, `npm run e2e`.
Expected: all green, including the full-pipeline journey.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers
git commit -m "docs: record the S3 runbook and mark the slice implemented"
```

---

## Post-slice

Merge the worktree branch to master per AGENTS.md, then a fresh-context whole-branch review (the S3 spec's own review rounds are done; this review covers the implementation). Any findings either get fixed in dedicated commits or land as timestamped backlog entries with commit links.
