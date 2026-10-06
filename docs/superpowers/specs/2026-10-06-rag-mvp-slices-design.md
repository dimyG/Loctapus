# RAG MVP — Slice Decomposition & S0+S1 Design

Date: 2026-10-06
Status: Approved design (pending user spec review)
Source of truth for product/architecture intent: `rag_mvp_agent_project_context.md` (the "MD"). This document records the decomposition decisions made during brainstorming and the detailed design for the first implementation slices. Where the two disagree, this document wins for the topics it covers.

## 1. Context and decisions from brainstorming

Environment (verified 2026-10-06):

- Windows 10, working dir `D:\Projects\RAG` (not yet a git repo at design time)
- Docker 29.6.2 + Docker Compose v5.3.1 available
- Python 3.14.7 venv at `.venv` (currently pip-only)
- Node 24.14.1 / npm 11.20.0 (for the later UI slice)

Decisions confirmed with the user:

1. **Planning scope**: full-MVP roadmap (coarse) + detailed plan only for the first slice(s). Later slices get their own design/planning round when reached.
2. **No provider API keys yet** (Unstructured, Voyage, Groq). The first end-to-end slice ships with stub providers behind the real provider interfaces so the whole pipeline runs offline. Stub providers are permanent, tested code — not throwaway.
3. **Monorepo**: backend and frontend live in this repo (`backend/` and `web/` top-level directories). They may be split into separate repos later — the clean top-level directory split keeps that extraction easy.
4. **Decomposition approach**: vertical slices (per MD §32), with the identity/projects work split out of the first retrieval slice into its own slice.

Guiding principles carried over from the MD (§29–30): replaceable providers behind explicit interfaces; free tiers first; monolith now with a clean internal `retrieval` module boundary; JWT auth; long-term user/workspace/team model with single-user flow; idempotent ingestion; transactional outbox; raw sources stored in S3/MinIO before parsing; structure-aware recursive chunking (replaceable); batched embeddings; RRF over lexical+vector; configurable rerank with `max_chunks_per_document`; `/retrieve` useful without `/answer`.

## 2. Slice roadmap

| Slice | Contents | Done when |
|---|---|---|
| **S0 — Scaffolding** | git init; backend layout; pyproject + deps; settings/config; docker-compose (Postgres+pgvector, RabbitMQ, MinIO); Alembic; `/health`; pytest harness | `docker compose up` → API healthy, tests run |
| **S1 — Identity & projects** | users/workspaces/teams tables (long-term model, single-user flow); JWT register/login; projects CRUD | Register → login → create/list/delete projects via API, all tested |
| **S2 — Ingestion → retrieval (stub providers)** | PDF/DOCX upload → MinIO; Celery ingestion (stub parser → normalize → chunk); chunks + outbox event in one transaction; outbox dispatcher → `embed` queue → stub embeddings; HNSW + GIN indexes; `POST /projects/{id}/retrieve` (vector + FTS + RRF, no rerank); basic `query_logs` | Upload a real PDF, get ranked grounded chunks back — fully offline |
| **S3 — Real providers + rerank + API keys** | Unstructured hosted parser; Voyage `voyage-4-lite` embeddings (dimension config + migration); Voyage `rerank-3-lite` + local diversity filter (`max_chunks_per_document`); project-scoped API keys authorizing `/retrieve` | Same flow works with real keys; `rerank=true/false` both work |
| **S4 — `/answer`** | LLM provider interface + Groq `openai/gpt-oss-20b`; grounded-context prompt; `/answer` calls retrieval internally | Question → answer grounded in cited chunks |
| **S5 — Ingestion robustness** | Idempotency hardening (`source_item_id, content_hash`); Celery Beat sync polling per `sources.sync_interval`; stale document/chunk replacement; source delete; retries + `ingestion_runs` status surfacing | Re-upload of a changed file replaces old chunks only after new ones are indexed |
| **S6 — Retrieval evaluation** | Labeling workflow over `query_logs`; Recall@K + MRR harness | Can score retrieval-config changes against a labeled set |
| **S7 — Web UI** | Devias Kit / React / Redux / Next.js in `web/`: landing, register/login, projects, upload + status, delete source, chat-style Q&A | Full MVP usable from a browser |
| **S8 — Website connector** (post-MVP) | sitemap discovery → HTTP fetch → HTML extraction → normalized document | Website source ingests via the same pipeline |

One implementation plan will cover **S0+S1 together** (both are small). S2 onward each get their own design round.

## 3. Repo layout (target)

Monorepo: everything lives in `D:\Projects\RAG`. `web/` arrives at S7; keeping backend and frontend in clean top-level directories makes a future repo split a simple directory extraction.

```
D:\Projects\RAG\
  backend/
    app/
      core/         # settings, security/JWT, db session, logging
      identity/     # users, workspaces, teams, auth endpoints + services
      projects/     # projects CRUD
      sources/      # (S2) sources, source_items, upload
      ingestion/    # (S2) connectors, chunking, pipeline tasks
      retrieval/    # (S2) query pipeline — clean module boundary, future service split
      providers/    # parser / embedding / reranker / llm interfaces + impls, selected via settings
      storage/      # (S2) S3/MinIO abstraction
      workers/      # (S2) celery app, tasks, outbox dispatcher
    alembic/
    tests/
    pyproject.toml
  web/              # (S7) Next.js frontend
  deploy/docker-compose.yml
  docs/
  .venv/            # existing Python venv, stays at repo root
```

Module rule: code after parsing works only on the normalized document model; provider-specific objects never cross the `providers/` boundary (MD §7, §30).

## 4. S1 detailed design — identity & projects

### 4.1 Data model (resolves MD §31 open decision #1)

Uses "workspace" naming from day one (MD §22 preference); preserves the long-term model so no redesign is needed later.

```
users                id (uuid pk), email (citext unique), password_hash, created_at
workspaces           id (uuid pk), name, owner_user_id -> users, is_personal bool
teams                id (uuid pk), workspace_id -> workspaces, name, is_personal bool
team_memberships     id (uuid pk), team_id -> teams, user_id -> users, unique(team_id, user_id)
projects             id (uuid pk), workspace_id -> workspaces, name, created_at
project_team_roles   id (uuid pk), project_id -> projects, team_id -> teams,
                     role text check in (admin|editor|viewer), unique(project_id, team_id)
```

`project_team_roles` exists from the start but has zero UI: registration creates the user + personal workspace + personal team + membership in one transaction; project creation auto-grants the creator's personal team the `admin` role. All project access checks scope through the user's teams, so team management later is pure UI/logic — no schema change.

### 4.2 Endpoints

```
POST /auth/register    {email, password} -> creates user+workspace+team+membership; returns JWT
POST /auth/login       {email, password} -> returns JWT
GET  /users/me         -> current user + personal workspace/team ids
POST /projects         {name} -> project (auto-grant personal team admin)
GET  /projects         -> projects visible to the user's teams
GET  /projects/{id}    -> project detail (404 if not visible)
DELETE /projects/{id}  -> delete project (admin role required)
```

### 4.3 Auth decisions

- JWT access token only, 24h expiry; no refresh token for MVP.
- Argon2 password hashing.
- Auth dependency: `get_current_user` (JWT) for S1; API-key auth joins it in S3 for `/retrieve` only.

### 4.4 Technical decisions

- **Sync SQLAlchemy 2.0** (models shared between FastAPI and Celery without async-session duplication; FastAPI runs sync endpoints in its threadpool).
- **Python 3.14** kept; downgrade to 3.12 only if a required wheel is actually missing.
- Dependency set (S0+S1): fastapi, uvicorn, sqlalchemy 2.x, psycopg[binary] v3, alembic, pydantic-settings, PyJWT, pwdlib[argon2], pytest, httpx (TestClient). Celery (RabbitMQ broker, no Redis) and boto3 arrive in S2.
- Dependency management: `backend/pyproject.toml` + pip in the existing root `.venv`.

## 5. S2 preview (detail deferred to S2 planning)

- **Upload flow**: `POST /projects/{id}/sources` (multipart) → raw file to MinIO → `sources` + `source_items` + `ingestion_runs` rows → enqueue ingestion → return source + status. Status polling via `GET /projects/{id}/sources`. Status values per MD §6: queued | fetching | processing | indexing | ready | failed.
- **Ingestion task**: fetch raw from MinIO → parser interface (stub: pypdf / python-docx; interface shaped for Unstructured's element model) → normalized document JSON → structure-aware recursive chunker (target 500–700 tokens, max ~1000, overlap ~80 — settings, not constants) → **one DB transaction**: document + chunks + `document_ready_for_embedding` outbox event → dispatcher (poll ~1s) publishes to RabbitMQ `embed` queue → embed worker batches stub embeddings → writes vectors → marks ready. Consumers idempotent (MD §19).
- **Retrieval**: `POST /projects/{id}/retrieve` → embed query → pgvector HNSW search + FTS `ts_rank` search → RRF → return top-k chunks with `heading_path` + source metadata → write `query_logs` row. Params: `query`, `top_k` (default 10), `rerank` (accepted, ignored until S3), `max_chunks_per_document` (accepted, applied locally from the start).

### Deferred open decisions — proposed defaults (finalized at S2/S3 planning)

| # (MD §31) | Decision | Proposed default |
|---|---|---|
| 3 | Normalized elements in Postgres | `documents.normalized_content` JSONB holding the elements array |
| 4 | Embedding dimension | Settings-driven `EMBEDDING_DIM`; pgvector column created per configured dim (stub: 384; voyage-4-lite dim set at S3) |
| 5 | RRF constant + candidate counts | k=60; 50 candidates per retriever; top-20 fused → rerank; final 10 — all in Settings |
| 6 | Query-log detail | Full MD §27 draft schema (ids + scores per stage) |
| 7 | S3 object-key convention | `raw/{project_id}/{source_item_id}/{content_hash}/{filename}` |
| 9 | Stale doc/chunk deletion | Replace-only-after-success (MD §20): old document + chunks deleted in the transaction that activates the replacement |

## 6. Testing approach

- TDD throughout (test first, then implementation).
- pytest against **real Postgres** from docker-compose (dedicated test database), never SQLite — pgvector/FTS behavior must be real from the start.
- API tests via FastAPI TestClient (httpx).
- S2 adds: worker/outbox integration tests against compose RabbitMQ, chunker unit tests with golden documents, retrieval tests with seeded stub embeddings.

## 7. Next step

Invoke the writing-plans skill to produce the S0+S1 implementation plan, then execute it via subagent-driven development with TDD.
