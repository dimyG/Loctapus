# S4 - Retrieval (stub providers) - Design

Date: 2026-10-19
Status: Approved design (2026-10-19 round); implementation pending.
Source of truth: `../../2026-10-06-initial_rag_mvp_agent_project_context.md` (the "MD") and
`2026-10-06-roadmap.md` (the "slices spec"). Where those disagree with this document on S4
topics, this document wins; where this document is silent, they govern.

## 1. Context

S4 is the retrieval backend slice (slices spec decision 7): `POST /api/projects/{id}/retrieve`
with stub query embeddings over the S3 indexes - pgvector HNSW cosine search plus Postgres FTS
`ts_rank` - fused with RRF, plus basic `query_logs`. No frontend ships in this slice: the S5 chat
view is the retrieval-facing UI from the start, so a standalone question view over raw ranked
chunks would be built only to be retired when the chat lands. This is the one-slice exception to
the backend+frontend pairing rule (slices spec decision 5); pairing resumes at S5.

Done-when (slices spec section 2): ask a question via the API, get ranked grounded chunks back -
fully offline.

S0-S3 are implemented on `master`. S3 left this slice ready: the HNSW
(`ix_chunks_embedding`, `vector_cosine_ops`) and GIN (`ix_chunks_search_vector`) indexes exist on
`chunks`, the stub embedding provider is deterministic (same text, same vector), and the startup
dimension guard is wired into the worker only - the API-side check was deferred to "S4 with the
retrieval path that actually needs it" (S3 spec decision 9). The backlog carries S4-relevant
notes: pin the `pgvector/pgvector` image tag (resolved here, decision 11), and HNSW `ef_search` /
`iterative_scan` tuning (stays deferred, section 10).

## 2. Decisions (2026-10-19 design round, user-approved)

1. **Endpoint and visibility.** `POST /api/projects/{project_id}/retrieve`, JSON body, JWT via
   `get_current_user` (API-key auth joins for `/retrieve` at S6 only). Access uses
   `get_project_visible_to_user` semantics exactly: team-visible through any role (viewer
   included) or `is_public`; otherwise `404 "project not found"`, matching the existing read
   endpoints (no existence leak). Roadmap S1: "queryable, once S4's `/retrieve` lands" by any
   authenticated user when `is_public`.
2. **Request.** `query` (string, stripped, non-empty, max 2000 chars), `top_k` (int, default 10,
   range 1..50), `rerank` (bool, default false - accepted, validated, logged, and ignored until
   S6), `max_chunks_per_document` (int >= 1, or `null` = unbounded, default `null`).
3. **Response.** `200` with a bare `list[RetrievedChunkOut]`: `{id, document_id, source_item_id,
   filename, position, heading_path, chunk_type, text, score}` where `score` is the fused RRF
   score. The `filename` join (chunks -> documents -> source_items) enriches only the final
   top_k rows, never the candidate legs. Empty index returns `[]` and still logs the query.
   Error paths log nothing (401/404/422).
4. **Vector leg.** `project_id = :pid AND embedding IS NOT NULL`, `ORDER BY embedding <=> :qv,
   id` (cosine distance, matching the `vector_cosine_ops` HNSW index), `LIMIT :candidates`. The
   query vector comes from the selected provider's `embed_query`. The `IS NOT NULL` filter is a
   correctness guard - a NULL embedding has NULL distance, sorts after every real distance, and
   would fill the result with useless rows whenever a project has fewer indexed chunks than the
   limit (embeddings still in flight) - and it lets the planner use the HNSW index scan.
5. **FTS leg.** `search_vector @@ websearch_to_tsquery('english', :q)`, `ORDER BY
   ts_rank(search_vector, websearch_to_tsquery('english', :q)) DESC, id`, same project filter **plus
   `embedding IS NOT NULL`** - both legs see the same fully-indexed candidate universe, so a
   half-embedded document never surfaces through only one leg - `LIMIT :candidates`.
   `websearch_to_tsquery` matches the computed `to_tsvector('english', text)` config, tolerates
   arbitrary user input (quoted phrases, `OR`, `-negation`), and an all-stopword query yields an
   empty tsquery and zero candidates - the vector leg still works, so the endpoint degrades
   gracefully.
6. **RRF fusion.** `score(chunk) = sum(1 / (rrf_k + rank_leg))` over the legs that returned it,
   1-based ranks, `rrf_k = 60` (setting, decision 9). Fused order: score desc, then the chunk's
   best (lowest) single-leg rank, then `id` - fully deterministic.
7. **Final selection: greedy diversity walk over the full fused ranking.** Walk fused order,
   skipping a chunk once its document has contributed `max_chunks_per_document` results, until
   `top_k` fills. When the cap leaves fewer survivors than `top_k`, the result is short -
   documented, not an error.
8. **`retrieval_fused_candidates` is deliberately absent until S6** (approved deviation from the
   roadmap table's "all in Settings" wording). The "top-20 fused" number is the reranker's input
   budget (MD section 13); at S4 nothing consumes it, and a setting read by nothing is fake
   configurability (S3 spec decision 4 precedent, `RAG_EMBEDDING_DIM`). S6 adds it together
   with the reranker, and the S6 `rerank=false` path then stays byte-identical to S4's walk
   (decision 7), while `rerank=true` becomes: fuse -> truncate to the budget -> rerank -> walk.
9. **Settings.** `retrieval_candidates_per_retriever = 50` (both legs' `LIMIT`, MD section 13
   "30-100 per retriever") and `rrf_k = 60`. Both positive-validated. No secrets, no new
   validators beyond positivity.
10. **`max_chunks_per_document` defaults to `null` (unbounded) at S4** (approved). The
    mechanism ships now and is tested with explicit values (roadmap: "applied locally from the
    start"); the product default is the S5 chat round's call, grounded in the consumer that
    sends it. Baking "3" into the API contract before the consumer exists would freeze an
    arbitrary value.
11. **Compose: pin the pgvector image.** `pgvector/pgvector:pg17` floats through pgvector
    releases (0.8.7 is current, 2026-10-01; 0.8.x alone shipped iterative scans and several
    HNSW fixes), and this slice adds the SQL that runs on it. Pin to
    `pgvector/pgvector:0.8.7-pg17`.
12. **`query_logs` is one JSONB-staged row per successful query** (deferred decision #6
    finalized, approved over the MD section 27 parallel-array draft). Column shape in section 4:
    `stages` JSONB holds `{vector, fts, fused, final}` with per-stage ids and scores. S6 appends
    a `rerank` stage in place - no migration; S8 labels over these rows. Parallel arrays were
    rejected: ids and scores can drift apart by index, and adding stages means a migration.
13. **API startup dimension guard.** A FastAPI lifespan handler runs on startup and reuses
    `app/ingestion/schema_guard.py`'s `run_startup_checks` unchanged - comparing the selected
    provider's `dimension` against the migrated `chunks.embedding` catalog type, refusing to
    serve on mismatch. The lifespan resolves its session factory through a module-level
    indirection (never `get_db`, and never a module-bound import of `SessionLocal`, which would
    freeze the dev engine at import time), so the test suite redirects it to the migration-built
    test engine - the same hermeticity rule as `get_db`. The refusal test monkeypatches the
    provider dimension and asserts `TestClient` startup raises. S3's worker guard stays as is;
    the API process embeds queries, so it needs the same check.
14. **Module layout.** New `app/retrieval/` package (section 6): `models.py` (`QueryLog`),
    `schemas.py`, `pipeline.py` (pure RRF fusion + diversity walk, no DB, no HTTP),
    `service.py` (the two legs, orchestration, log write), `router.py`. `pipeline.py` stays
    importable without SQLAlchemy so its unit tests run without a database. `app/main.py` gains
    the router include, the lifespan, and `app.retrieval.models` registration through
    `app/models.py`. The package keeps the roadmap section 3 "future service split" boundary:
    no provider objects cross into it beyond `EmbeddingProvider`, no HTTP objects cross out
    beyond the response schema.

## 3. API contract

```
POST /api/projects/{project_id}/retrieve
Authorization: Bearer <jwt>

{
  "query": "how do I rotate the garage key",
  "top_k": 10,                          // optional, default 10, 1..50
  "rerank": false,                      // optional, default false, ignored until S6
  "max_chunks_per_document": null       // optional, default null (unbounded), >= 1
}

200 ->
[
  {
    "id": "uuid", "document_id": "uuid", "source_item_id": "uuid",
    "filename": "handbook.pdf", "position": 7, "heading_path": ["Setup", "Keys"],
    "chunk_type": "text", "text": "...", "score": 0.0328
  }
]
```

- `401` without a valid token; `404 "project not found"` when neither team-visible nor public;
  `422` for an empty/whitespace query, a query over 2000 chars, or `top_k` /
  `max_chunks_per_document` out of range (pydantic).
- `rerank: true` is accepted and echoed into `query_logs.params`; it changes nothing at S4.
  This is the contract S6 activates.
- Validation bounds (2000 chars, top_k 1..50) are constants in `app/retrieval/schemas.py`,
  not settings: they are API contract limits, not tuning knobs.

## 4. `query_logs`

One row per successful query, written in the same request session after selection completes.
`latency_ms` measures embed -> legs -> fuse -> select; the row's own insert is excluded
(documented in the model docstring).

```
id          uuid pk
project_id  uuid  -> projects.id ON DELETE CASCADE
user_id     uuid  -> users.id            (no ON DELETE action; users are never deleted in MVP)
query       text                          (as received, stripped)
params      jsonb                         (request echo + effective settings, below)
latency_ms  integer
stages      jsonb                         (per-stage ids and scores, below)
created_at  timestamptz  server_default now()
index ix_query_logs_project_id_created_at (project_id, created_at)
```

`params`:

```json
{
  "top_k": 10,
  "rerank": false,
  "max_chunks_per_document": null,
  "settings": {
    "rrf_k": 60,
    "candidates_per_retriever": 50,
    "embedding_provider": "stub"
  }
}
```

`stages` (vector/fts entries ordered by rank; fused ordered by fused score; final ordered):

```json
{
  "vector": [{"chunk_id": "uuid", "score": 0.211}],
  "fts":    [{"chunk_id": "uuid", "score": 0.034}],
  "fused":  [{"chunk_id": "uuid", "score": 0.0328}],
  "final":  ["uuid", "uuid"]
}
```

- `vector.score` is the cosine distance (`<=>`, lower is better) and `fts.score` the `ts_rank`
  (higher is better); they are never compared with each other - RRF ranks only. Each entry
  records which it is by its stage key.
- `final` ids are the response order; `fused` covers every candidate (up to
  `2 x candidates_per_retriever`), so S8 can rescore any past selection.

## 5. Pipeline

```
query
  -> embed_query (selected provider, stub)
  -> vector leg (project filter, <=> , id tie-break, LIMIT 50)
  -> fts leg    (project filter, websearch_to_tsquery + ts_rank, id tie-break, LIMIT 50)
  -> rrf fuse   (k = rrf_k, deterministic tie-breaks)
  -> greedy diversity walk (max_chunks_per_document, top_k)
  -> enrich top_k rows with filename (join documents -> source_items)
  -> write query_logs row
  -> respond
```

- Both legs run even when one is empty: a stopword-only query still returns vector candidates;
  a zero-vector query still returns FTS candidates. A leg is skipped only on zero candidates.
- The stub hash-bag embedding makes the vector leg behave like soft lexical overlap, so seeded
  tests can predict ranked output exactly (the whole slice is offline-testable).
- The walk consumes the *full* fused ranking (decision 7), so document skew cannot under-fill
  `top_k` while diverse candidates sit beyond a truncation point.

## 6. Module layout

```
backend/
  app/
    retrieval/
      __init__.py
      models.py     # QueryLog
      schemas.py    # RetrieveIn, RetrievedChunkOut, validation constants
      pipeline.py   # fuse_rrf + select_final: pure, no SQLAlchemy import
      service.py    # legs, orchestration, query_logs write
      router.py     # the endpoint
    main.py         # + lifespan guard, + router include
    models.py       # + app.retrieval.models registration
  alembic/versions/ # + one revision: create query_logs
  tests/retrieval/
    test_pipeline.py       # pure fusion + walk
    test_service.py       # legs + logging against real Postgres
    test_retrieve_api.py  # endpoint contract
    test_startup_guard.py # lifespan refusal
```

## 7. Settings, migration, compose

- Settings (section 2 decision 9): `retrieval_candidates_per_retriever = 50`, `rrf_k = 60`.
- One Alembic revision creating `query_logs` (section 4). No chunk or index changes: S3 built
  both indexes this slice queries.
- Compose (section 2 decision 11): `pgvector/pgvector:pg17` -> `pgvector/pgvector:0.8.7-pg17`.
  Resolves the backlog pin item.

## 8. Testing approach

- **Pure unit** (`test_pipeline.py`): RRF sums over one/both legs, k constant applied, fused
  ordering with deterministic tie-breaks; walk caps per document, preserves fused order, skips
  capped documents, under-fills short, `null` cap never skips.
- **Service, real Postgres, rollback fixture** (`test_service.py`): seeded chunks with stub
  embeddings; known-token query returns the expected chunk via the vector leg, keyword query
  via FTS; `embedding IS NULL` rows excluded from both legs; another project's chunks never
  return; `max_chunks_per_document` respected; `query_logs` row written once per query with
  params, ordered stages, and a positive `latency_ms`.
- **API** (`test_retrieve_api.py`): 401; 404 for an invisible project; public project queryable
  by a non-member; 422 for empty query / oversized query / `top_k` bounds / bad
  `max_chunks_per_document`; `rerank: true` accepted and ignored; empty index returns `[]` and
  still logs.
- **Startup guard** (`test_startup_guard.py`): mismatched provider dimension refuses startup
  through the lifespan (section 2 decision 13).
- Full `ruff check`, `ruff format --check`, `mypy app tests`, `pytest` gate (AGENTS.md).

## 9. Out of scope (recorded, not built)

- S5: chat UI as the retrieval-facing UI; `/answer` grounded context; the product default for
  `max_chunks_per_document`.
- S6: `rerank` activation behind a `Reranker` provider interface (Voyage `rerank-3-lite`),
  `retrieval_fused_candidates` as its input budget, real providers, API keys.
- S8: Recall@K / MRR harness over `query_logs.stages`.

## 10. Risks and deferred

- **HNSW `ef_search` / `iterative_scan` tuning stays in the backlog.** Test-scale data cannot
  show recall differences; revisit with real corpus scale at S6.
- **`ts_rank` weight detail**: the computed `search_vector` carries no rank weights (plain
  `to_tsvector`); acceptable for MVP (MD section 11: "PostgreSQL FTS ranking is not BM25").
- **Query length bound (2000 chars) is a constant, not a setting** - if S6's real providers
  need different limits, that slice moves it.
- **No pagination/offset** on `/retrieve`: `top_k <= 50` bounds every response; programmatic
  paging arrives with API-key consumers at S6 if asked for.
- **Log growth**: `query_logs` grows unbounded; retention/pruning is an S7+ infrastructure
  concern, not designed here.