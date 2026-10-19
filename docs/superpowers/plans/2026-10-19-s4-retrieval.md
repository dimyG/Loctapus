# S4 Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `POST /api/projects/{id}/retrieve` - stub query embedding, pgvector HNSW cosine leg + Postgres FTS leg, RRF fusion, greedy per-document diversity walk, per-query `query_logs` - backend only, fully offline.

**Architecture:** A new `app/retrieval/` package keeps the future-service boundary: `pipeline.py` is pure (no SQLAlchemy) RRF fusion + diversity selection, `service.py` runs the two SQL legs and writes the log row, `router.py` maps to response schemas. A FastAPI lifespan runs the S3-dimension startup guard in the API process. One Alembic revision adds `query_logs`. No frontend (slices spec decision 7).

**Tech Stack:** FastAPI, SQLAlchemy 2.0 sync, pgvector (`cosine_distance`), Postgres FTS (`websearch_to_tsquery`, `ts_rank`), Alembic, pytest against real compose Postgres.

**Spec:** `../specs/2026-10-19-s4-retrieval-design.md` (decisions 1-14 are this plan's contract; section 3 is the API shape, section 4 the `query_logs` shape).

**Worktree:** Execute in a dedicated worktree off `master` (repo rule: every task in a worktree so parallel work cannot interfere).

## Global Constraints

- Ruff line length 110; docstrings on every module/class/function, private ones too (`tests/test_style.py` enforces); blank line after every docstring; comments start capitalized, end with a period.
- All parameters keyword-only (`def f(*, a, b)`), including calls to third-party code; no `# type: ignore` unless unavoidable; precise annotations.
- Gates before every commit: `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest` (run from `backend/`, against the compose Postgres).
- `rerank` is accepted, logged, ignored (spec decision 2). `max_chunks_per_document` default `null` (decision 10). No `retrieval_fused_candidates` setting exists at S4 (decision 8) - do not add one.
- Both legs filter `embedding IS NOT NULL` (spec decisions 4-5, amended `c71b2e3`).
- `query` validation: strip, reject empty, max 2000 chars (constant, not a setting). `top_k` default 10, 1..50 (inline Field bounds, not settings).
- Commit style: one concern per commit; never add agent co-author lines.

## Review Focus

Input classes the spec implies but no happy path exercises - each pinned by the named test in its owning task:

1. A chunk whose embedding is still NULL (mid-ingestion document) must not surface in either leg - `test_fts_leg_excludes_null_embeddings` (Task 4).
2. A stopword-only query ("the") must not error; the FTS leg returns nothing and the vector leg still serves - `test_stopword_only_query_uses_vector_leg_only` (Task 4).
3. Malformed websearch syntax (stray quotes) must parse tolerantly, never 500 - `test_malformed_websearch_syntax_is_tolerated` (Task 4).
4. `top_k` larger than the fused pool must return a short list, not an error or padding - `test_select_final_underfills_short_pool` (Task 1).
5. Another project's chunks must never leak into results - `test_legs_are_scoped_to_the_project` (Task 4).

## Task DAG

```
T1 pipeline (pure) ──┐
T2 query_logs model ─┼──> T4 settings+schemas+service ──> T5 router+api ──> T6 pin+gates
T3 startup guard ───┘
```

T1, T2, T3 are mutually independent (disjoint files) and may run in parallel. T4 consumes T1+T2. T5 consumes T4 and coexists with T3 (both touch `app/main.py` and `tests/conftest.py`; serialize T3 before T5 in a single-execution run). T6 consumes all.

---

### Task 1: Pure RRF fusion and diversity walk

**Files:**
- Create: `backend/app/retrieval/__init__.py` (module docstring only)
- Create: `backend/app/retrieval/pipeline.py`
- Test: `backend/tests/retrieval/__init__.py`, `backend/tests/retrieval/test_pipeline.py`

**Interfaces:**
- Consumes: nothing (no SQLAlchemy, no settings import - keeps the file importable without a database).
- Produces (used by Task 4):

```python
@dataclass(frozen=True)
class StageCandidate:
    """One leg's ranked result row: chunk identity plus the leg's raw score."""
    chunk_id: UUID
    document_id: UUID
    score: float

@dataclass(frozen=True)
class FusedCandidate:
    """One RRF-fused candidate: chunk identity plus the fused RRF score."""
    chunk_id: UUID
    document_id: UUID
    score: float

def fuse_rrf(*, vector: list[StageCandidate], fts: list[StageCandidate], rrf_k: int) -> list[FusedCandidate]:
    """Fuse both legs' rank-ordered candidates with RRF; input order is rank order."""

def select_final(
    *, fused: list[FusedCandidate], top_k: int, max_chunks_per_document: int | None
) -> list[FusedCandidate]:
    """Walk fused order, skipping past-cap documents, collecting top_k."""
```

- [ ] **Step 1: Write the failing tests** in `tests/retrieval/test_pipeline.py`

Tests with exact expectations (build candidates with `uuid4()` ids, distinct `document_id`s per document):

- `test_fuse_sums_both_legs`: a chunk at vector rank 1 and fts rank 2 with `rrf_k=60` scores `1/(60+1) + 1/(60+2)` and outranks a chunk appearing in one leg only.
- `test_fuse_uses_one_based_ranks`: first position in a leg contributes `1/(rrf_k+1)`.
- `test_fuse_orders_by_score_then_best_rank_then_id`: two chunks with equal fused score order by best single-leg rank; exact ties (same ranks) order by `chunk_id` ascending.
- `test_fuse_handles_empty_leg`: one leg empty still fuses the other.
- `test_select_final_preserves_fused_order_and_truncates`: `top_k=2` over three fused candidates returns the first two, in order.
- `test_select_final_caps_per_document`: three candidates from one document and two from another, `max_chunks_per_document=1`, `top_k=3` returns rank-1 of doc A, rank-1 of doc B, rank-2 of doc A (skipping doc A's between-ranks chunk only per the cap).
- `test_select_final_null_cap_never_skips`: `max_chunks_per_document=None` returns the top_k regardless of document skew.
- `test_select_final_underfills_short_pool`: `top_k=10` over two candidates returns both.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/retrieval/test_pipeline.py -v`
Expected: FAIL (module `app.retrieval.pipeline` does not exist).

- [ ] **Step 3: Implement `pipeline.py`**

`fuse_rrf`: build `best_rank` per `chunk_id` walking both lists (1-based); score = sum of `1/(rrf_k + rank)` over legs containing the chunk; sort by `(-score, best_rank, chunk_id)`. `select_final`: iterate fused order, count per `document_id`, append when `max_chunks_per_document is None` or count < cap, stop at `top_k`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/retrieval/test_pipeline.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add app/retrieval/ tests/retrieval/
git commit -m "feat(retrieval): add pure rrf fusion and diversity selection"
```

---

### Task 2: `query_logs` model, migration, registry

**Files:**
- Create: `backend/app/retrieval/models.py`
- Create: `backend/alembic/versions/0006_query_logs.py`
- Modify: `backend/app/models.py` (registry import)
- Test: `backend/tests/test_alembic.py` (extend)

**Interfaces:**
- Consumes: `app.core.models.Base` (house pattern: `sources/models.py`).
- Produces: `QueryLog` ORM (used by Task 4): columns `id` (uuid pk), `project_id` (FK `projects.id` ON DELETE CASCADE), `user_id` (FK `users.id`, no action), `query` (Text), `params` (JSONB), `latency_ms` (Integer), `stages` (JSONB), `created_at` (DateTime tz, `server_default=func.now()`).

- [ ] **Step 1: Write the failing tests** in `tests/test_alembic.py`

- `test_query_logs_table_exists`: `{"query_logs"} <= set(inspect(conn).get_table_names())` (mirror `test_ingestion_tables_exist`).
- Extend `test_foreign_key_columns_are_indexed`'s `expected` dict with `"query_logs": {"project_id", "user_id"}` - both FKs must have a leading-column index (`project_id` leads the composite `(project_id, created_at)`; `user_id` gets its own).

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_alembic.py -v`
Expected: FAIL (table `query_logs` does not exist; the FK-index assertion misses).

- [ ] **Step 3: Implement model, migration, registry**

`app/retrieval/models.py`: `QueryLog` exactly as the Produces block, house style - `ForeignKeyConstraint` entries in `__table_args__`, `Index("ix_query_logs_project_id_created_at", "project_id", "created_at")`, `Index("ix_query_logs_user_id", "user_id")`.

`alembic/versions/0006_query_logs.py`: match `0005_ingestion_outbox.py` header style (`revision: str = "0006"`, `down_revision = "0005"`). `upgrade()`: `op.create_table("query_logs", ...)` with `sa.Uuid()` columns, `sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE")`, `sa.ForeignKeyConstraint(["user_id"], ["users.id"])`, then `op.create_index("ix_query_logs_project_id_created_at", ...)` and `op.create_index("ix_query_logs_user_id", ...)`. `downgrade()`: drop both indexes, then the table.

`app/models.py`: add `from app.retrieval import models as retrieval_models  # noqa: F401` (alphabetical position between `projects` and `sources`).

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_alembic.py tests/test_model_registry.py -v`
Expected: PASS - including `test_models_match_migrations` (autogenerate sees no diff), `test_migrations_downgrade_to_base`, `test_single_head_revision`, and the registry walker.

- [ ] **Step 5: Commit**

```bash
git add app/retrieval/models.py app/models.py alembic/versions/0006_query_logs.py tests/test_alembic.py
git commit -m "feat(retrieval): add query_logs schema"
```

---

### Task 3: API startup dimension guard (lifespan)

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/conftest.py` (client fixture)
- Test: `backend/tests/retrieval/test_startup_guard.py`

**Interfaces:**
- Consumes: `app.ingestion.schema_guard.run_startup_checks(*, db, embedding_provider)` unchanged (S3 code), `app.providers.get_embedding_provider(*, settings)`, `app.core.db.SessionLocal`.
- Produces: `app.main.lifespan` attached to the FastAPI app. No later task consumes it; every `client`-fixture test exercises it at TestClient startup.

- [ ] **Step 1: Write the failing tests** in `tests/retrieval/test_startup_guard.py`

```python
def test_lifespan_runs_startup_checks(*, engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check the lifespan runs the dimension guard at startup."""
    monkeypatch.setattr("app.main.SessionLocal", sessionmaker(bind=engine))
    calls: list[object] = []
    monkeypatch.setattr("app.main.run_startup_checks", lambda *, db, embedding_provider: calls.append(db))
    with TestClient(app):
        pass
    assert calls

def test_guard_refuses_mismatched_dimension(*, engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check a provider dimension that disagrees with the catalog refuses startup."""
    monkeypatch.setattr("app.main.SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr("app.main.get_embedding_provider", lambda *, settings: _mismatched())
    with pytest.raises(RuntimeError, match="chunks.embedding is vector"):
        with TestClient(app):
            pass
```

`_mismatched()` returns a private stub class with `dimension: int = 9999` (docstring + keyword-only style rules apply).

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/retrieval/test_startup_guard.py -v`
Expected: FAIL (`app.main` has no `SessionLocal`/`run_startup_checks` attributes; `setattr` raises `AttributeError`).

- [ ] **Step 3: Implement the lifespan in `app/main.py`**

```python
@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Run the embedding dimension guard once per process before serving."""
    session = SessionLocal()
    try:
        run_startup_checks(db=session, embedding_provider=get_embedding_provider(settings=get_settings()))
    finally:
        session.close()
    yield
```

Wire `lifespan=lifespan` into the `FastAPI(...)` constructor. Imports: `from collections.abc import AsyncIterator`, `from contextlib import asynccontextmanager`, `from app.core.db import SessionLocal`, `from app.ingestion.schema_guard import run_startup_checks`, `from app.providers import get_embedding_provider`.

**Also modify the conftest `client` fixture** (same concern - without this, every API test's TestClient startup would hit the dev database): add a `monkeypatch: pytest.MonkeyPatch` parameter and `monkeypatch.setattr("app.main.SessionLocal", sessionmaker(bind=engine))` before constructing the client; import `sessionmaker` there.

- [ ] **Step 4: Run the full suite to verify nothing regressed**

Run: `pytest -v`
Expected: PASS - every existing `client`-fixture test now boots through the patched guard (dimension 384 matches the test catalog).

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/conftest.py tests/retrieval/test_startup_guard.py
git commit -m "feat(api): run the embedding dimension guard in the lifespan"
```

---

### Task 4: Settings, schemas, retrieval service

**Files:**
- Modify: `backend/app/core/config.py` (two settings)
- Modify: `backend/tests/test_config.py` (positivity), `backend/tests/factories.py` (seeding helper)
- Create: `backend/app/retrieval/schemas.py`, `backend/app/retrieval/service.py`
- Test: `backend/tests/retrieval/test_service.py`

**Interfaces:**
- Consumes: `StageCandidate`, `FusedCandidate`, `fuse_rrf`, `select_final` (Task 1); `QueryLog` (Task 2); `get_embedding_provider`, `EmbeddingProvider` (providers); `Chunk`, `Document` (`app.ingestion.models`), `SourceItem`, `Source` (`app.sources.models`).
- Produces (Task 5 consumes):

```python
MAX_QUERY_CHARS: Final = 2000  # schemas.py

class RetrieveIn(BaseModel):
    """One retrieval request body."""
    query: str  # stripped, non-empty, max MAX_QUERY_CHARS
    top_k: int = 10           # Field(ge=1, le=50)
    rerank: bool = False      # accepted and ignored until S6
    max_chunks_per_document: int | None = None  # Field(ge=1)

class RetrievedChunkOut(BaseModel):
    """One final retrieval result as served by the API."""
    id: UUID; document_id: UUID; source_item_id: UUID; filename: str
    position: int; heading_path: list[str]; chunk_type: str; text: str; score: float

@dataclass(frozen=True)
class RetrievedChunk:  # service.py - domain row the router maps via _to_out
    """One final result row: chunk fields, source filename, and fused score."""
    id: UUID; document_id: UUID; source_item_id: UUID; filename: str
    position: int; heading_path: list[str]; chunk_type: str; text: str; score: float

def retrieve(
    *, db: Session, project_id: UUID, user_id: UUID, params: RetrieveIn, settings: Settings
) -> list[RetrievedChunk]:
    """Run both legs, fuse, select, enrich, and log one query."""
```

- Private but tested directly: `_search_vector_leg(*, db: Session, project_id: UUID, query_vector: list[float], limit: int) -> list[StageCandidate]` and `_search_fts_leg(*, db: Session, project_id: UUID, query: str, limit: int) -> list[StageCandidate]` - both ordered per spec decisions 4-5 (id tie-break), both `embedding IS NOT NULL`.
- Settings (config.py, pydantic `Field(gt=0)`, placed after `max_upload_mb`): `retrieval_candidates_per_retriever: int = 50`, `rrf_k: int = 60`.
- `tests/factories.py` addition (used by Tasks 4-5 tests): `seed_document_with_chunks(*, db: Session, project_id: UUID, filename: str = "doc.pdf", chunk_texts: list[str], embed: bool = True) -> SeededDocument` - reuses/creates the project's upload `Source` (same pattern as `seed_upload`), one new `SourceItem`, one `Document` (`normalized_content={}`), one `Chunk` per text (`position=enumerate`, `heading_path=[]`, `chunk_metadata={"filename": filename}`, sha256 `content_hash`, `embedding` from `StubEmbeddingProvider().embed_documents(texts=chunk_texts)` when `embed=True` else `None`); no run, no outbox row, no commit. `SeededDocument` frozen dataclass: `document_id`, `source_item_id`, `chunk_ids`.

- [ ] **Step 1: Write the failing settings test** in `tests/test_config.py`

`test_retrieval_settings_reject_nonpositive` (parametrized over `"retrieval_candidates_per_retriever"` and `"rrf_k"`, value `0`): constructing `Settings` with a non-positive value raises pydantic `ValidationError`. Follow the file's existing Settings-construction pattern.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (unknown field - `Settings` has no `extra` on those names).

- [ ] **Step 3: Add the settings**

Add the two `Field(gt=0)` settings to `app/core/config.py` per the Produces block.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing service tests** in `tests/retrieval/test_service.py`

Seeding: `seed_project` + `seed_document_with_chunks` from `tests/factories.py`. Tests:

- `test_vector_leg_orders_by_cosine_distance`: seed texts `"alpha alpha bravo"`, `"alpha"`, `"charlie"` in one document each; `_search_vector_leg` with `StubEmbeddingProvider().embed_query(text="alpha bravo")` returns them in that exact order (hash-bag cosine is deterministic).
- `test_fts_leg_orders_by_ts_rank`: seed `"the quick brown fox jumps"` and `"quick silver"`; `_search_fts_leg(query="quick")` ranks the fox chunk first (more matches).
- `test_fts_leg_excludes_null_embeddings`: seed one document `embed=False`; its chunks never appear in `_search_fts_leg` nor `_search_vector_leg` even with a matching query.
- `test_stopword_only_query_uses_vector_leg_only`: `retrieve(query="the", ...)` against a seeded chunk containing `"the the"` returns that chunk through the vector leg while the FTS leg contributes nothing (assert via the written `QueryLog.stages`: `stages["fts"] == []`).
- `test_malformed_websearch_syntax_is_tolerated`: `retrieve(query='alpha "or OR', ...)` - no exception; returns a list.
- `test_legs_are_scoped_to_the_project`: seed two projects; `retrieve` on project A never returns project B's chunk ids.
- `test_retrieve_applies_max_chunks_per_document`: three chunks in doc A outrank one chunk in doc B (construct texts so `"alpha"` matches A's chunks most); `max_chunks_per_document=1`, `top_k=2` returns A-rank-1 and B-rank-1.
- `test_retrieve_writes_one_query_log_row`: after `retrieve`, exactly one `QueryLog` row exists for the project: `query` matches the stripped input, `params["top_k"]`/`["rerank"]`/`["max_chunks_per_document"]` echo the request, `params["settings"]["rrf_k"]` is 60, `stages` keys are `{"vector", "fts", "fused", "final"}`, `final` ids equal the returned chunk ids in order, `latency_ms >= 0`.
- `test_retrieve_enriches_filename_and_source_item`: returned `RetrievedChunk.filename` and `source_item_id` match the seeded item.
- `test_retrieve_empty_project_returns_empty_and_logs`: no chunks seeded; `retrieve` returns `[]` and still writes one log row with `stages["final"] == []`.

- [ ] **Step 6: Run to verify failure**

Run: `pytest tests/retrieval/test_service.py -v`
Expected: FAIL (`app.retrieval.service` does not exist).

- [ ] **Step 7: Implement `schemas.py` and `service.py`**

`schemas.py`: `RetrieveIn` per the Produces block - `query` validated by a `field_validator` that strips and raises `ValueError("query must not be empty")` on empty (whitespace-only queries 422), `Field(max_length=MAX_QUERY_CHARS)` for the length cap; `RetrievedChunkOut` field-for-field.

`service.py`: `retrieve` orchestration exactly per spec section 5 - `perf_counter` start; `embed_query`; both legs (`limit=settings.retrieval_candidates_per_retriever`); `fuse_rrf(rrf_k=settings.rrf_k)`; `select_final(top_k=params.top_k, max_chunks_per_document=params.max_chunks_per_document)`; enrichment join (`Chunk` join `Document` on ids join `SourceItem` on ids, filtered by final ids, `Chunk.id.in_`); `latency_ms` measured embed through selection (log write excluded); `QueryLog` row with `params` echo + settings snapshot (`{"rrf_k", "candidates_per_retriever", "embedding_provider"}`) + `stages` (`{"vector", "fts", "fused", "final"}`, UUIDs stringified); `db.add` + `db.commit`. Vector leg: `Chunk.embedding.cosine_distance(query_vector)`; FTS leg: `func.websearch_to_tsquery("english", query)` matched via `Chunk.search_vector.op("@@")` and ranked via `func.ts_rank`; both `.filter(Chunk.project_id == project_id, Chunk.embedding.is_not(None))`, `.order_by(..., Chunk.id)`, `.limit(limit)`. Keep the leg ordering comments per spec decisions 4-5.

- [ ] **Step 8: Run to verify pass**

Run: `pytest tests/retrieval/ tests/test_config.py -v`
Expected: PASS (all pipeline, service, config tests).

- [ ] **Step 9: Commit**

```bash
git add app/core/config.py app/retrieval/schemas.py app/retrieval/service.py tests/test_config.py tests/factories.py tests/retrieval/test_service.py
git commit -m "feat(retrieval): add settings, schemas, and the retrieval service"
```

---

### Task 5: Router and API wiring

**Files:**
- Create: `backend/app/retrieval/router.py`
- Modify: `backend/app/main.py` (include the router)
- Test: `backend/tests/retrieval/test_retrieve_api.py`

**Interfaces:**
- Consumes: `retrieve` and `RetrievedChunk` (Task 4), `get_current_user` (`app.identity.dependencies`), `get_project_visible_to_user` (`app.projects.service`), `get_db`, `get_settings`, conftest `client` fixture (Task 3's patch included).
- Produces: `POST /api/projects/{project_id}/retrieve` (registered via `app.include_router(retrieval_router, prefix="/api")`).

- [ ] **Step 1: Write the failing tests** in `tests/retrieval/test_retrieve_api.py`

House pattern: `client` + `db_session` fixtures, `tests/helpers.py` auth header helpers, `factories.seed_document_with_chunks` for data.

- `test_retrieve_requires_auth`: no bearer token on a seeded project path -> `401`.
- `test_retrieve_404_for_invisible_project`: second registered user, first user's project id -> `404 "project not found"`.
- `test_retrieve_works_for_public_project_non_member`: owner sets `is_public` via `PATCH /api/projects/{id}`; a non-member retrieves -> `200` with results.
- `test_retrieve_validation_errors` (parametrized): `{"query": "   "}`, `{"query": "x" * 2001}`, `{"query": "x", "top_k": 0}`, `{"query": "x", "top_k": 51}`, `{"query": "x", "max_chunks_per_document": 0}` -> `422`.
- `test_retrieve_strips_and_matches`: `{"query": "  alpha  "}` returns the chunk seeded with `"alpha"` text.
- `test_rerank_true_accepted_and_ignored`: same seeded project, `{"query": "alpha", "rerank": true}` returns the identical list as `rerank: false`.
- `test_retrieve_empty_project_returns_empty_list`: no chunks -> `200 []`, and one `QueryLog` row exists.
- `test_retrieve_response_shape`: response items carry exactly `id`, `document_id`, `source_item_id`, `filename`, `position`, `heading_path`, `chunk_type`, `text`, `score`; `score` is a float; order is fused rank (first item's text contains the seeded `"alpha"` tokens).
- `test_top_k_defaults_and_limits`: omitting `top_k` returns at most 10 of 12 seeded chunks.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/retrieval/test_retrieve_api.py -v`
Expected: FAIL (route does not exist - 404 on POST).

- [ ] **Step 3: Implement the router and wire it**

`router.py` (house style: `sources/router.py`):

```python
@router.post("/projects/{project_id}/retrieve", response_model=list[RetrievedChunkOut])
def retrieve_chunks(
    *, project_id: UUID, body: RetrieveIn, user: User = Depends(get_current_user),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> list[RetrievedChunkOut]:
    """Return fused, diversity-selected grounded chunks for one query."""
```

Body: `get_project_visible_to_user(db=db, user=user, project_id=project_id)`; `None` -> `HTTPException(404, "project not found")`; then `retrieve(db=db, project_id=project.id, user_id=user.id, params=body, settings=settings)`; map each `RetrievedChunk` through `_to_out` (explicit field mapping, house pattern). `app/main.py`: import and `app.include_router(retrieval_router, prefix="/api")` after `sources_router`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/retrieval/ tests/test_api_prefix.py tests/test_cors.py -v`
Expected: PASS - the prefix test now sees the new route under `/api`.

- [ ] **Step 5: Commit**

```bash
git add app/retrieval/router.py app/main.py tests/retrieval/test_retrieve_api.py
git commit -m "feat(api): expose POST /projects/{id}/retrieve"
```

---

### Task 6: Compose pgvector pin and full-branch gates

**Files:**
- Modify: `deploy/docker-compose.yml` (db image tag)
- Modify (as needed): `docs/superpowers/backlog.md`

**Interfaces:**
- Consumes: nothing from other tasks; runs the whole-branch gates.
- Produces: pinned db image; a green branch; residual deferrals recorded.

- [ ] **Step 1: Pin the db image**

`deploy/docker-compose.yml`: `image: pgvector/pgvector:pg17` -> `image: pgvector/pgvector:0.8.7-pg17` (spec decision 11; current pgvector release 0.8.7, 2026-10-01). Same Postgres major, so the existing `pgdata` volume stays compatible.

- [ ] **Step 2: Verify the compose file still parses**

Run: `docker compose -f deploy/docker-compose.yml config`
Expected: exit 0, rendered config prints with the new tag.

- [ ] **Step 3: Commit the pin**

```bash
git add deploy/docker-compose.yml
git commit -m "build(deploy): pin the pgvector image to 0.8.7-pg17"
```

- [ ] **Step 4: Run the full gates**

Run from `backend/`: `ruff check .` then `ruff format --check .` then `mypy app tests` then `pytest`.
Expected: all green. Any failure is a defect in an earlier task - fix it in the owning task's files with its own commit, then rerun.

- [ ] **Step 5: Backlog residuals**

Append any deferrals this branch's reviews raised to `docs/superpowers/backlog.md` under a timestamped `## 2026-10-19 - S4 retrieval` header, each line linking its commit. The known carried deferrals stay put (HNSW `ef_search`/`iterative_scan`, README web sections, warnings cleanup). If nothing new was raised, skip - do not create an empty section.

- [ ] **Step 6: Commit the backlog**

```bash
git add docs/superpowers/backlog.md
git commit -m "docs(backlog): record the s4 residuals"
```