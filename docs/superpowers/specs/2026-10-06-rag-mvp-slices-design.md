# RAG MVP — Slice Decomposition & S0+S1 Design

Date: 2026-10-06
Updated: 2026-10-19
Status: Approved design. S0-S3 are implemented on `master`. Roadmap re-cut on 2026-10-09: the web UI is pulled forward to S2 and, from S2 on, every slice pairs its backend work with the matching frontend part (decision 5 below). Roadmap re-cut on 2026-10-12: the former S3 is split into an upload+ingestion slice and a retrieval slice (decision 6 below). Roadmap re-cut on 2026-10-19: S4 loses its query UI (retrieval backend only), the former S6 - `/answer` + chat UI with a free-tier LLM - moves ahead of the real-providers slice as S5, and the former S5 - real providers + rerank + API keys - becomes S6 (decision 7 below).
Source of truth for product/architecture intent: `../../2026-10-06-initial_rag_mvp_agent_project_context.md` (the "MD"). This document records the decomposition decisions made during brainstorming and the detailed design for the first implementation slices. Where the two disagree, this document wins for the topics it covers.

## 1. Context and decisions from brainstorming

Environment (verified 2026-10-06):

- Windows 10, working dir `D:\Projects\RAG` (not yet a git repo at design time)
- Docker 29.6.2 + Docker Compose v5.3.1 available
- Python 3.14.7 venv at `.venv` (currently pip-only)
- Node 24.14.1 / npm 11.20.0 (for the web UI, which landed at S2)

Decisions confirmed with the user:

1. **Planning scope**: full-MVP roadmap (coarse) + detailed plan only for the first slice(s). Later slices get their own design/planning round when reached.
2. **No provider API keys yet** (Unstructured, Voyage, Groq). The first end-to-end slice ships with stub providers behind the real provider interfaces so the whole pipeline runs offline. Stub providers are permanent, tested code — not throwaway.
3. **Monorepo**: backend and frontend live in this repo (`backend/` and `web/` top-level directories). They may be split into separate repos later — the clean top-level directory split keeps that extraction easy.
4. **Decomposition approach**: vertical slices (per MD §32), with the identity/projects work split out of the first retrieval slice into its own slice.
5. **Web UI pulled forward; every slice pairs backend + frontend** (confirmed 2026-10-09): S0+S1 are implemented, so the next slice stands up the web UI instead of ingestion. The former standalone web-UI slice (old S7) is dissolved: its features are merged into the slices that build the backend they display. S2 wires `web/` (Devias Kit / React / Redux on Vite - a pure client-side SPA; the MD's Next.js (§2, §24) was superseded on 2026-10-09) to the existing identity/projects API - register/login/logout and projects list + create, nothing more. From S2 on, each slice ships its backend work together with its matching frontend part, so every slice is testable end-to-end from the browser.
6. **S3 split into upload+ingestion and retrieval** (confirmed 2026-10-12): the former S3 carried both the full ingestion pipeline (upload → parse → chunk → outbox → embed) and the retrieval endpoint, which is too much scope for one slice. It is split into S3 (upload flow + ingestion task + upload/status UI) and S4 (retrieval flow + query UI); the former S4-S8 shift to S5-S9.
7. **No retrieval UI; `/answer` + chat ahead of real providers** (confirmed 2026-10-19): the S4 query UI (question view over raw ranked chunks) is dropped - the chat UI built with `/answer` is the retrieval-facing UI from the start, so no standalone query view is built only to be retired once the chat lands. This carves a one-slice exception out of decision 5's pairing rule: S4 ships the retrieval backend alone; the pairing resumes at S5. The former S6 (`/answer` + chat UI) becomes S5 so the full question → grounded-answer path works from the browser before any real-provider investment; its LLM runs on Groq's free tier (`openai/gpt-oss-20b`, the MD §16 cost-first choice), the first server-side provider key. The former S5 (real providers + rerank + API keys) becomes S6.

Guiding principles carried over from the MD (§29–30): replaceable providers behind explicit interfaces; free tiers first; monolith now with a clean internal `retrieval` module boundary; JWT auth; long-term user/workspace/team model with single-user flow; idempotent ingestion; transactional outbox; raw sources stored in S3/MinIO before parsing; structure-aware recursive chunking (replaceable); batched embeddings; RRF over lexical+vector; configurable rerank with `max_chunks_per_document`; `/retrieve` useful without `/answer`.

## 2. Slice roadmap

| Slice | Contents | Done when |
|---|---|---|
| **S0 - Scaffolding** ✅ done | git init; backend layout; pyproject + deps; settings/config; docker-compose (Postgres+pgvector, RabbitMQ, MinIO (replaced by Garage in S3)); Alembic; `/health`; pytest harness | `docker compose up` → API healthy, tests run |
| **S1 - Identity & projects** ✅ done | users/workspaces/teams tables (long-term model, single-user flow); JWT register/login; projects CRUD | Register → login → create/list/delete projects via API, all tested |
| **S2 - Web UI foundations** ✅ done | Devias Kit / React / Redux on Vite (SPA) in `web/`: landing; register/login/logout; projects list + create (team picked from the user's workspaces/teams), wired to the existing S1 API | Register → login → logout → list/create projects from a browser, all tested |
| **S3 - Upload & ingestion (stub providers) + upload UI** ✅ done | PDF/DOCX upload → Garage; Celery ingestion (stub parser → normalize → chunk); chunks + outbox event in one transaction; outbox dispatcher → `embed` queue → stub embeddings; HNSW + GIN indexes; frontend: project page, upload PDF/DOCX, processing status | Upload a real PDF from the browser and watch it reach `ready` - fully offline |
| **S4 - Retrieval (stub providers)** | `POST /projects/{id}/retrieve` (vector + FTS + RRF, no rerank); basic `query_logs`; no frontend - the chat UI built at S5 is the retrieval-facing UI (decision 7) | Ask a question via the API, get ranked grounded chunks back - fully offline |
| **S5 - `/answer` + chat UI (free-tier LLM)** | LLM provider interface + Groq `openai/gpt-oss-20b` on the free tier; grounded-context prompt; `/answer` calls retrieval internally; frontend: chat view on the project page - answer in a simple AI-chat style with cited chunks | Question → answer grounded in cited chunks, from the browser |
| **S6 - Real providers + rerank + API keys + keys UI** | Unstructured hosted parser; Voyage `voyage-4-lite` embeddings (dimension config + migration); Voyage `rerank-3-lite` + local diversity filter (`max_chunks_per_document`); project-scoped API keys authorizing `/retrieve`; frontend: project API-key management; rerank + `max_chunks_per_document` controls in the S5 chat UI | Same flow works with real keys; `rerank=true/false` both work from the chat UI |
| **S7 - Ingestion robustness + source management UI** | Idempotency hardening (`source_item_id, content_hash`); sync polling per `sources.sync_interval` (scheduler decided at S7's round); stale document/chunk replacement; file delete and replace; retries + `ingestion_runs` status surfacing; frontend: file delete, ingestion-run status in the project page | Re-upload of a changed file replaces old chunks only after new ones are indexed; visible in the UI |
| **S8 - Retrieval evaluation + labeling UI** | Labeling workflow over `query_logs`; Recall@K + MRR harness; frontend: labeling workflow UI over `query_logs` | Can score retrieval-config changes against a labeled set |
| **S9 - Website connector** (post-MVP) | sitemap discovery → HTTP fetch → HTML extraction → normalized document; frontend: add-website-source flow | Website source ingests via the same pipeline, from the browser |

S0+S1 were implemented under one plan (`../plans/2026-10-06-s0-s1-scaffolding-identity-projects.md`, plus follow-up review-fix rounds); S2 under `../plans/2026-10-09-s2-web-ui-foundations.md` (plus review-fix rounds). **S3 onward each get their own design round, and every slice pairs its backend work with its matching frontend part** (decision 5; S4 is the backend-only exception - its frontend is the S5 chat UI, decision 7) so backend and frontend land and are tested together.

## 3. Repo layout (target)

Monorepo: everything lives in `D:\Projects\RAG`. `web/` landed at S2; keeping backend and frontend in clean top-level directories makes a future repo split a simple directory extraction.

```
D:\Projects\RAG\
  backend/
    app/
      core/         # settings, security/JWT, db session, logging
      identity/     # users, workspaces, teams, auth endpoints + services
      projects/     # projects CRUD
      sources/      # (S3) sources, source_items, upload
      ingestion/    # (S3) connectors, chunking, pipeline tasks
      retrieval/    # (S4) query pipeline — clean module boundary, future service split
      providers/    # parser / embedding / reranker / llm interfaces + impls, selected via settings
      storage/      # (S3) S3 abstraction (Garage in dev)
      workers/      # (S3) celery app, tasks, outbox dispatcher
    alembic/
    tests/
    pyproject.toml
  web/              # (S2) React + Vite SPA frontend
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
workspaces           id (uuid pk), name, owner_user_id -> users
teams                id (uuid pk), workspace_id -> workspaces, name
team_memberships     id (uuid pk), team_id -> teams, user_id -> users, unique(team_id, user_id)
projects             id (uuid pk), workspace_id -> workspaces, name, is_public bool, created_at
project_team_roles   id (uuid pk), project_id -> projects, team_id -> teams,
                     role text check in (admin|editor|viewer), unique(project_id, team_id)
revoked_tokens       jti (text pk), expires_at, revoked_at
```

`project_team_roles` exists from the start but has zero UI: registration creates the user + Default workspace + Default team + membership + a Default project in one transaction; project creation takes an explicit `team_id` (the caller must be a member of that team) and auto-grants that team the `admin` role. All project access checks scope through the user's teams, so team management later is pure UI/logic - no schema change. `projects.is_public` makes a project viewable (and queryable, once S4's `/retrieve` lands) by any authenticated user; only team `admin`s can edit or delete it.

### 4.2 Endpoints

```
POST /auth/register    {email, password} -> creates user+Default workspace+team+membership+Default project; returns JWT
POST /auth/login       {email, password} -> returns JWT
POST /auth/logout      -> revokes the presented token (per-session); 204
GET  /users/me         -> current user (id, email) only
GET  /workspaces       -> workspaces the user's teams belong to
GET  /workspaces/{id}/teams -> teams in a workspace the user belongs to
POST /projects         {name, team_id} -> project (grants that team admin; 404 if not a member)
GET  /projects         -> team-scoped projects visible to the user
GET  /projects/public  -> all public projects (is_public=true)
GET  /projects/{id}    -> project detail (404 if not team-visible and not public)
PATCH /projects/{id}   -> update name and/or is_public (admin role required)
DELETE /projects/{id}  -> delete project (admin role required)
```

### 4.3 Auth decisions

- JWT access token only, 24h expiry; no refresh token for MVP. Tokens carry a `jti` claim; `POST /auth/logout` records it in `revoked_tokens` for per-session revocation, checked centrally in `get_current_user`.
- Argon2 password hashing.
- Auth dependency: `get_current_user` (JWT) for S1; API-key auth joins it in S6 for `/retrieve` only.

### 4.4 Technical decisions

- **Sync SQLAlchemy 2.0** (models shared between FastAPI and Celery without async-session duplication; FastAPI runs sync endpoints in its threadpool).
- **Python 3.14** kept; downgrade to 3.12 only if a required wheel is actually missing.
- Dependency set (S0+S1): fastapi, uvicorn, sqlalchemy 2.x, psycopg[binary] v3, alembic, pydantic-settings, PyJWT, pwdlib[argon2], pytest, httpx (TestClient). Celery (RabbitMQ broker, no Redis) and boto3 arrive in S3.
- Dependency management: `backend/pyproject.toml` + pip in the existing root `.venv`.

## 5. Next-slices preview (detail deferred to each slice's planning)

### S2 - Web UI foundations (✅ done)

Devias Kit / React / Redux SPA on Vite in `web/` (the MD's Next.js (§2, §24) superseded on 2026-10-09; no SSR and no Node server - FastAPI stays the sole server, serving the JSON API), wired to the existing S1 endpoints: landing; register/login/logout; projects list + create (team picked from the user's workspaces/teams). Implemented on `master` under `../plans/2026-10-09-s2-web-ui-foundations.md` (app structure, auth-state handling, CORS with the FastAPI backend, frontend test approach).

### S3 - Upload & ingestion (stub providers) + upload UI (✅ done)

Implemented on `master` under `../plans/2026-10-13-s3-upload-ingestion.md` (design: `2026-10-12-s3-upload-ingestion-design.md`, amended by the 2026-10-14 review fixes - the uploads API, the run state machine, the composite project scope, the outbox backoff, and the worker hardening described there supersede this preview).

- **Upload flow**: `POST /projects/{id}/sources` (multipart) → raw file to Garage → `sources` + `source_items` + `ingestion_runs` rows → enqueue ingestion → return source + status. Status polling via `GET /projects/{id}/sources`. Status values per MD §6: queued | fetching | processing | indexing | ready | failed.
- **Ingestion task**: fetch raw from Garage → parser interface (stub: pypdf / python-docx; interface shaped for Unstructured's element model) → normalized document JSON → structure-aware recursive chunker (target 500–700 tokens, max ~1000, overlap ~80 — settings, not constants) → **one DB transaction**: document + chunks + `document_ready_for_embedding` outbox event → dispatcher (poll ~1s) publishes to RabbitMQ `embed` queue → embed worker batches stub embeddings → writes vectors → marks ready. Consumers idempotent (MD §19).
- **Indexes**: HNSW on the pgvector embedding column + GIN for full-text search, created with this slice's schema; S4's retrieval queries rely on them.
- **Frontend pairing**: project page with upload + processing status.

#### Deferred open decisions - proposed defaults (finalized at S3 planning)

| # (MD §31) | Decision | Proposed default |
|---|---|---|
| 3 | Normalized elements in Postgres | `documents.normalized_content` JSONB holding the elements array |
| 4 | Embedding dimension | The provider constant `STUB_EMBEDDING_DIM` (stub: 384), not a setting: the migration hardcodes the literal and the startup guard cross-checks the constant; Voyage's dim lands with its own migration at S6 |
| 7 | S3 object-key convention | `raw/{project_id}/{source_item_id}/{content_hash}/{filename}` |
| 9 | Stale doc/chunk deletion | Replace-only-after-success (MD §20): old document + chunks deleted in the transaction that activates the replacement |

### S4 - Retrieval (stub providers)

- **Retrieval**: `POST /projects/{id}/retrieve` → embed query → pgvector HNSW search + FTS `ts_rank` search → RRF → return top-k chunks with `heading_path` + source metadata → write `query_logs` row. Params: `query`, `top_k` (default 10), `rerank` (accepted, ignored until S6), `max_chunks_per_document` (accepted, applied locally from the start).
- **No frontend** (decision 7): the retrieval-facing UI is the S5 chat view; a standalone question view over raw chunks would be built only to be retired once the chat lands.

#### Deferred open decisions - proposed defaults (finalized at S4 planning)

| # (MD §31) | Decision | Proposed default |
|---|---|---|
| 5 | RRF constant + candidate counts | k=60; 50 candidates per retriever; top-20 fused → rerank; final 10 — all in Settings |
| 6 | Query-log detail | Full MD §27 draft schema (ids + scores per stage) |

### S5 - `/answer` + chat UI (free-tier LLM)

- **LLM provider interface** (MD §16: abstraction so OpenAI or another LLM can replace Groq later) + **Groq `openai/gpt-oss-20b` on the free tier** - the first server-side provider key; a stub LLM implementation keeps the test suite offline, per the decision-2 provider pattern.
- **`/answer` flow** (MD §16): call `/retrieve` internally → build the grounded context from the final chunks → prompt instructs answering from the supplied context only → return the answer with its cited chunks; `/retrieve` stays independently useful.
- **Frontend pairing**: chat view on the project page - ask → answer in a simple AI-chat style with cited chunks; the ranked grounded chunks surface as the answer's citations.

### S6 - Real providers + rerank + API keys (former S5)

- **Provider swaps behind the existing interfaces**: Unstructured hosted parser replaces the stub; Voyage `voyage-4-lite` embeddings (dimension config + migration + re-embedding of stored chunks); Voyage `rerank-3-lite` + the local diversity filter activate the `rerank` param.
- **Project-scoped API keys** authorize `/retrieve` (programmatic access); frontend: project API-key management; rerank + `max_chunks_per_document` controls join the S5 chat UI.

## 6. Testing approach

- TDD throughout (test first, then implementation).
- pytest against **real Postgres** from docker-compose (dedicated test database), never SQLite — pgvector/FTS behavior must be real from the start.
- API tests via FastAPI TestClient (httpx).
- S2 adds: frontend tests covering the register/login/logout and projects list/create flows (frontend test approach decided at the S2 design round).
- S3 adds: worker/outbox integration tests against compose RabbitMQ, chunker unit tests with golden documents.
- S4 adds: retrieval tests with seeded stub embeddings.
- S5 adds: `/answer` pipeline tests against a stub LLM implementation; chat UI tests.

## 7. Next step

S0-S3 are complete on `master`. Next: brainstorming/design round + implementation plan for **S4 - Retrieval (stub providers)** (`POST /projects/{id}/retrieve`: vector + FTS + RRF over the S3 indexes; backend only - the chat UI lands with S5), then execution via subagent-driven development with TDD. Each later slice follows the same pattern, with backend + matching frontend designed and tested together (S4 the backend-only exception, decision 7).
