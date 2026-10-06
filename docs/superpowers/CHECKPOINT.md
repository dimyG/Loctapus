# Session Checkpoint — 2026-10-06

> **For the agent continuing this work:** This file captures everything done and decided so far. Read it fully, then read the two documents referenced below before acting. The immediate next step is in §7.

## 1. Project

RAG MVP — a Kapa.ai-like ingestion and retrieval service (FastAPI, PostgreSQL+pgvector+FTS, RabbitMQ, Celery, MinIO, React/Next.js UI later).

- **Authoritative product/architecture spec:** `rag_mvp_agent_project_context.md` (repo root, committed). Referred to as "the MD".
- **Agreed slice decomposition + S0/S1 design:** `docs/superpowers/specs/2026-10-06-rag-mvp-slices-design.md` (committed). Where it conflicts with the MD, the design spec wins for topics it covers.
- **Working dir / repo:** `D:\Projects\RAG` — git repo initialized in this session, branch `master`, 2 commits:
  - `7d50fe9` Add project context and slice decomposition design spec
  - `b062dde` Switch to monorepo layout: backend/ + web/ in one repo

## 2. Environment (verified)

- Windows 10, Git Bash shell. **All file paths must be absolute Windows paths with backslashes** (harness bug workaround).
- Docker 29.6.2 + Compose v5.3.1 available.
- Python 3.14.7 venv at `D:\Projects\RAG\.venv` (pip-only, no packages yet). Decision: keep 3.14; downgrade to 3.12 only if a wheel is actually missing.
- Node 24.14.1 / npm 11.20.0 (needed only at UI slice S7).

## 3. Decisions confirmed by the user (do not re-litigate)

1. **Planning scope:** full-MVP roadmap (coarse) + detailed plan only for the first slice(s). Later slices get their own design round.
2. **No external API keys yet** (Unstructured / Voyage / Groq). First end-to-end slice ships **stub providers** (local pypdf/python-docx parser, deterministic hash-based embeddings) behind the real provider interfaces — permanent tested code, not throwaway. Real providers become a config swap in slice S3.
3. **Monorepo:** backend + frontend in this repo as `backend/` and `web/` top-level dirs (user reversed an earlier "two repos" decision). Split possible later via directory extraction.
4. **Decomposition:** vertical slices per MD §32. User explicitly asked to split the original big end-to-end slice: **identity + projects CRUD is its own slice (S1)**, separate from the ingestion/retrieval slice (S2).

## 4. Slice roadmap (renumbered, agreed)

- **S0** Scaffolding: layout, deps, docker-compose (Postgres+pgvector, RabbitMQ, MinIO), Alembic, `/health`, pytest harness
- **S1** Identity & projects: users/workspaces/teams tables (long-term model, single-user flow), JWT register/login, projects CRUD
- **S2** Ingestion → retrieval with stub providers: upload → MinIO → Celery parse/chunk → transactional outbox → embed worker → HNSW+GIN → `POST /projects/{id}/retrieve` (vector+FTS+RRF) + `query_logs`
- **S3** Real providers (Unstructured, Voyage `voyage-4-lite`, Voyage `rerank-3-lite` + diversity filter) + project-scoped API keys
- **S4** `/answer` (LLM interface + Groq `openai/gpt-oss-20b`)
- **S5** Ingestion robustness: idempotency, Celery Beat sync, stale-document replacement, source delete, retries
- **S6** Retrieval evaluation: labeling + Recall@K / MRR
- **S7** Web UI in `web/` (Devias Kit / React / Redux / Next.js)
- **S8** Website connector (post-MVP)

**One implementation plan covers S0+S1 together.** That plan is what we were about to write.

## 5. Key S0/S1 design points (from the spec — full detail there)

- Repo layout: `backend/app/{core,identity,projects,sources,ingestion,retrieval,providers,storage,workers}/`, `backend/{alembic,tests}/`, `backend/pyproject.toml`, `deploy/docker-compose.yml`, `.venv` stays at repo root.
- Identity schema: `users`, `workspaces` (owner_user_id, is_personal), `teams`, `team_memberships`, `projects` (workspace_id), `project_team_roles` (role admin|editor|viewer — table exists now, zero UI; registration auto-creates personal workspace+team+membership; project creation auto-grants personal team admin).
- Endpoints: `POST /auth/register`, `POST /auth/login` → JWT, `GET /users/me`, `POST /projects`, `GET /projects`, `GET /projects/{id}`, `DELETE /projects/{id}`.
- Auth: JWT access token only, 24h expiry, no refresh token for MVP; argon2 password hashing.
- Tech: **sync SQLAlchemy 2.0** (shared with Celery later), FastAPI, psycopg[binary] v3, Alembic, pydantic-settings, PyJWT, pwdlib[argon2], pytest + httpx TestClient.
- Testing: TDD throughout; pytest against **real Postgres from docker-compose** (never SQLite); S2 adds worker/outbox integration tests.
- Deferred open decisions with proposed defaults (finalize at S2/S3 planning): normalized_content JSONB; settings-driven `EMBEDDING_DIM` (stub 384); RRF k=60, 50 candidates/retriever, top-20→rerank, final 10; full query_logs schema; S3 keys `raw/{project_id}/{source_item_id}/{content_hash}/{filename}`; replace-only-after-success for stale docs.

## 6. Process state (superpowers skills)

- `superpowers:brainstorming` — **completed** (spec written, self-reviewed, user-reviewed and approved).
- `superpowers:writing-plans` — **JUST INVOKED, in progress.** The skill content was loaded; no plan file written yet.
- Task list state: tasks #1–#7 completed; task #8 "Invoke writing-plans skill" is in_progress.

## 7. IMMEDIATE NEXT STEP

Write the **S0+S1 implementation plan** per the loaded `superpowers:writing-plans` skill:

1. Announce: "I'm using the writing-plans skill to create the implementation plan."
2. Save to `docs/superpowers/plans/2026-10-06-s0-s1-scaffolding-identity-projects.md` with the required header (goal, architecture, tech stack, spec link to `docs/superpowers/specs/2026-10-06-rag-mvp-slices-design.md`, Global Constraints section).
3. Bite-sized TDD tasks (failing test → run → implement → run → commit), exact file paths, real code in every step, no placeholders. Include the file-structure map before tasks.
4. Self-review (spec coverage, placeholder scan, type consistency), fix inline.
5. Commit the plan, then offer execution choice: **Subagent-Driven (recommended)** vs Inline Execution.
