# Comment and Docstring Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite every docstring and comment in the Python backend and React frontend to the approved standard (clear, concise, junior-developer-readable, Sphinx `:param:` / JSDoc `@param` parameter lists), filling gaps where comments are missing.

**Architecture:** Eleven vertical slices, each grouping a backend package + its tests + the consuming frontend feature, executed in DAG order. Every slice is a comments/docstrings-only change verified by the existing toolchain; the spec travels with this plan and is the source of the style standard.

**Tech Stack:** Python 3.14, ruff, mypy, pytest; React + TypeScript, ESLint, Vitest, tsc; Git worktree `comment-docstring-rewrite` on branch `comment-docstring-rewrite`.

**Spec:** `docs/superpowers/specs/2026-11-09-comment-docstring-rewrite-design.md` - the plan argues from the spec; executors read both. The spec's "The standard" section is normative for all wording decisions.

## Global Constraints

- Model: **only `opencode/mimo-v2.6-flash-free`** for all execution, subagents, and reviews (spec's model constraint; overrides AGENTS.md model list for this task).
- Diff touches **only comments and docstrings**; executable lines never change. Where a comment disagrees with the code, rewrite the comment to match the code.
- No em dashes anywhere; comments capitalized and ending with a period; line length 110 (Python); blank line after every docstring (enforced by `tests/test_style.py`).
- Python: every function/method with parameters gets one `:param name:` line per parameter, no `:type:` lines. Frontend: every export gets preceding JSDoc with `@param {type} name - ...` lines where it takes parameters.
- Test docstrings: imperative "Check that..." voice, one line.
- One concern per commit, `docs(<scope>): ...` message, no co-author trailer. Untracked files get their own dedicated commit.
- Verification per slice (amended by user ruling mid-execution): backend `ruff check .`, `ruff format --check .`, and `pytest tests/test_style.py` in `backend/`; frontend `npm run lint` and `npm run format:check` in `web/`. Format/style checks only - the full `pytest` and `npm run test` suites run once, at the end, in Task 11.

## Review Focus

Conditions the spec implies but no task's automated tests exercise - each pinned to its owning task's manual step:

1. **An executable line changed by accident** - a comment rewrite silently alters code. Pinned by every task's "Diff scan" step (manual `git diff` review for non-comment hunks).
2. **`ruff format` reflows or fails on new multi-line docstrings** - Pinned by every backend task's verification step (`ruff format --check .`).
3. **A stale spec ID corrected to the wrong target** (S6 to S7, `R2`, `decision N`) - Pinned by Task 11's cross-cutting stale-reference audit.
4. **A `:param:` line naming a parameter that does not exist** (signature drift while rewriting ~754 docstrings) - Pinned by `mypy`/`pytest` not catching it, so each backend task's Diff scan step explicitly checks param lists against signatures.
5. **Prettier rewraps or rejects rewritten JSDoc/comments** - Pinned by `npm run format:check` in every frontend task's verification.

## Task DAG

Arrows mean depends on; siblings run in parallel.

```
1 ──► 2 ──► 3 ──► 4 ──► 6 ──► 7
│            │     │            │
│            │     └──► 8       │
└──► 5 ──────┴── (5 free after 1)
└──► 9 ──────────────────────► 10 ──► 11
```

---

### Task 1: Core & bootstrap slice

**Files:**
- Modify: `backend/app/core/config.py`, `backend/app/core/db.py`, `backend/app/core/models.py`, `backend/app/core/security.py`, `backend/app/core/__init__.py`, `backend/app/main.py`, `backend/app/models.py`
- Modify: `backend/alembic/env.py`, `backend/alembic/versions/*.py` (7 migrations), `backend/scripts/*.py` (4 files)
- Modify: `backend/tests/conftest.py`, `backend/tests/__init__.py`, `backend/tests/core/*.py`, `backend/tests/test_config.py`, `backend/tests/test_alembic.py`, `backend/tests/test_style.py`
- Modify: `web/src/main.tsx`, `web/src/app/api.ts`, `web/src/app/api.test.ts`, `web/src/app/store.ts`, `web/src/app/hooks.ts`, `web/src/app/sectionPaths.ts`, `web/src/app/sectionPaths.test.ts`, `web/src/app/lastProject.ts`, `web/src/app/App.tsx`, `web/src/app/App.test.tsx`, `web/src/app/AppRoutes.tsx`, `web/src/app/BootSplash.tsx`

**Interfaces:**
- Consumes: nothing (root task; establishes the applied examples of the spec's standard).
- Produces: the reference comment style all later tasks copy - especially multi-line docstrings with `:param:` lists in `app/core` and JSDoc with `@param` in `web/src/app/api.ts`.

- [ ] **Step 1: Rewrite stale/wrong text first**

Fix any comment in these files that is factually wrong, references a moved/renamed artifact, or is duplicated within a file. Known: none flagged in this slice; verify `alembic/env.py` gets a module docstring (it is the only Python file without one).

- [ ] **Step 2: Fill gaps**

Add missing docstrings/`@param` lists/why-comments so no file in the slice would leave a junior developer lost. Priority: `web/src/main.tsx` and the zero-comment test files (`api.test.ts`, `sectionPaths.test.ts`), and inline why-commentary in `core/security.py` and `core/config.py`.

- [ ] **Step 3: Rewrite the rest of the slice to the standard**

Apply the spec's "The standard" section to every remaining docstring and comment in the slice, including converting one-line Python docstrings to summary + `:param:` list form and adding JSDoc to undocumented exports (`hooks.ts` `useAppSelector`, `store.ts` slice state types).

- [ ] **Step 4: Verify backend**

Run in `backend/`: `ruff check .` then `ruff format --check .` then `mypy app tests` then `pytest`.
Expected: all four pass (0 failures, 0 formatting diffs).

- [ ] **Step 5: Verify frontend**

Run in `web/`: `npm run lint` then `npx tsc -b` then `npm run test` then `npm run format:check`.
Expected: all four pass.

- [ ] **Step 6: Diff scan**

Run `git diff` and confirm: every hunk is comment/docstring-only; no executable line changed; every `:param:` name matches a real parameter of its function; no em dashes.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core backend/app/main.py backend/app/models.py backend/alembic backend/scripts backend/tests web/src/main.tsx web/src/app/api.ts web/src/app/api.test.ts web/src/app/store.ts web/src/app/hooks.ts web/src/app/sectionPaths.ts web/src/app/sectionPaths.test.ts web/src/app/lastProject.ts web/src/app/App.tsx web/src/app/App.test.tsx web/src/app/AppRoutes.tsx web/src/app/BootSplash.tsx
git commit -m "docs(core): rewrite comments and docstrings to the new standard"
```

---

### Task 2: Identity & auth slice

**Files:**
- Modify: `backend/app/identity/*.py` (6 files), `backend/tests/identity/*.py`
- Modify: `web/src/features/auth/*.ts(x)` (7 files + tests), `web/src/lib/tokenStorage.ts` + test, `web/src/app/RequireAuth.tsx` + test

**Interfaces:**
- Consumes: comment style from Task 1; `app/core/security.py` session/token behavior.
- Produces: corrected conflict-target comment in `app/identity/service.py:72` (truthful description of `on_conflict_do_nothing()` with no conflict target); `tokenStorage.ts` backlog pointer kept valid.

- [ ] **Step 1: Fix known stale text**

Rewrite `app/identity/service.py:72`'s comment to describe actual behavior (no conflict target is passed; a duplicate insert raises and is handled by the caller/flow as the code actually does). Keep `docs/backlog.md:580-585` entry; confirm it still matches reality after the rewrite.

- [ ] **Step 2: Fill gaps**

Add missing why-commentary in `identity/router.py` and `identity/dependencies.py` (currently docstring-only), JSDoc for any undocumented export in `features/auth`.

- [ ] **Step 3: Rewrite the rest of the slice to the standard**

- [ ] **Step 4: Verify backend** (same four commands as Task 1 Step 4) Expected: all pass.

- [ ] **Step 5: Verify frontend** (same four commands as Task 1 Step 5) Expected: all pass.

- [ ] **Step 6: Diff scan** (same checks as Task 1 Step 6)

- [ ] **Step 7: Commit**

```bash
git commit -m "docs(identity): rewrite comments and docstrings to the new standard"
```
(Stage `backend/app/identity`, `backend/tests/identity`, `web/src/features/auth`, `web/src/lib`, `web/src/app/RequireAuth*`.)

---

### Task 3: Projects & workspaces slice

**Files:**
- Modify: `backend/app/projects/*.py` (5 files), `backend/tests/projects/*.py`
- Modify: `web/src/features/projects/*.ts(x)` (8 files + tests), `web/src/features/workspaces/*.ts` (2 files)

**Interfaces:**
- Consumes: Task 1 style; identity/team context from Task 2.
- Produces: documented `projectsApi`/`workspacesApi` exports later slices reuse.

- [ ] **Step 1: Fix stale/wrong/duplicated text** (none known; verify during rewrite)
- [ ] **Step 2: Fill gaps** - priority: `projects/router.py` (106 lines, zero inline why-commentary), `projectsApi.ts` and `workspacesApi.ts` exports, `ProjectsPage.test.tsx:87-94` opaque `vi.waitFor` chain.
- [ ] **Step 3: Rewrite the rest of the slice to the standard**
- [ ] **Step 4: Verify backend** Expected: all four pass.
- [ ] **Step 5: Verify frontend** Expected: all four pass.
- [ ] **Step 6: Diff scan** (Task 1 Step 6 checks)
- [ ] **Step 7: Commit** - `docs(projects): rewrite comments and docstrings to the new standard` (stage `backend/app/projects`, `backend/tests/projects`, `web/src/features/projects`, `web/src/features/workspaces`)

---

### Task 4: Sources, uploads & ingestion slice

**Files:**
- Modify: `backend/app/sources/*.py` (5 files), `backend/app/ingestion/*.py` (7 files), `backend/app/storage/service.py` + `__init__.py`, `backend/app/outbox/*.py` (2 files)
- Modify: `backend/tests/sources/*.py`, `backend/tests/ingestion/*.py`, `backend/tests/storage/*.py`, `backend/tests/outbox/*.py`
- Modify: `web/src/features/sources/*.ts(x)` (7 files + tests), `web/src/features/uploads/*.ts(x)` (7 files + tests)

**Interfaces:**
- Consumes: Task 1 style; project context from Task 3.
- Produces: deduplicated `ingestion/service.py` comments (the ×4 connection-failure comment collapses to one per file); collapse the ×3 `project_id is repeated...` block in `ingestion/models.py`/`sources/models.py` to once per file.

- [ ] **Step 1: Fix stale/wrong/duplicated text**

Collapse the known duplicate groups: `app/ingestion/service.py` ×4 comment (lines ~291, 306, 352, 481), `app/conversations` ×3 is NOT in this slice (Task 7), `project_id` block ×3 across `ingestion/models.py` + `sources/models.py` (once per file), `End the read transaction` ×3 (once per file), duplicated blocks in `tests/sources/test_uploads_api.py`.

- [ ] **Step 2: Fill gaps** - priority: `sources/router.py`, `storage/service.py`, zero-comment test flows, `UploadDropzone`/`FileUploadPage` why-commentary.
- [ ] **Step 3: Rewrite the rest of the slice to the standard** (includes `app/ingestion/chunking.py` - keep its good why-comments nearly verbatim).
- [ ] **Step 4: Verify backend** Expected: all four pass.
- [ ] **Step 5: Verify frontend** Expected: all four pass.
- [ ] **Step 6: Diff scan** (Task 1 Step 6 checks)
- [ ] **Step 7: Commit** - `docs(ingestion): rewrite comments and docstrings to the new standard` (stage the four backend packages + their tests + `web/src/features/sources`, `web/src/features/uploads`)

---

### Task 5: Providers slice (parallel after Task 1)

**Files:**
- Modify: `backend/app/providers/base.py`, `groq_llm.py`, `stub_embeddings.py`, `stub_llm.py`, `stub_parser.py`, `__init__.py`
- Modify: `backend/tests/providers/*.py`

**Interfaces:**
- Consumes: Task 1 style; retrieval/answers slices (6, 7) call `get_llm_provider()` / `get_embedding_provider()` / `get_parser()` - signatures unchanged.
- Produces: de-triplicated factory docstrings in `providers/__init__.py`, each with an accurate summary and `:param:` list.

- [ ] **Step 1: Fix stale/wrong/duplicated text**

Replace the three identical factory docstrings in `providers/__init__.py` with distinct, accurate ones (each factory dispatches on a different setting).

- [ ] **Step 2: Fill gaps** - priority: `providers/base.py` (85 lines, zero inline why-commentary).
- [ ] **Step 3: Rewrite the rest of the slice to the standard**
- [ ] **Step 4: Verify backend** Expected: all four pass. (No frontend files in this slice.)
- [ ] **Step 5: Diff scan** (Task 1 Step 6 checks)
- [ ] **Step 6: Commit** - `docs(providers): rewrite comments and docstrings to the new standard`

---

### Task 6: Retrieval slice

**Files:**
- Modify: `backend/app/retrieval/*.py` (5 files), `backend/tests/retrieval/*.py`

**Interfaces:**
- Consumes: Task 1 style; ingested chunks from Task 4; `pipeline.py`'s "no SQLAlchemy" module boundary must stay stated.
- Produces: corrected "S6 reranker" comment in `app/retrieval/schemas.py:34` (feature is S7; correct the ID or drop it).

- [ ] **Step 1: Fix stale/wrong/duplicated text** - `retrieval/schemas.py:34` S6 to S7 correction.
- [ ] **Step 2: Fill gaps** - `retrieval/router.py` (50 lines, docstring-only), `test_retrieve_api.py` (197 lines, zero inline comments).
- [ ] **Step 3: Rewrite the rest of the slice to the standard** - keep `pipeline.py`'s RRF/tie-break detail, re-expressed per the standard (summary + `:param:` list; algorithm detail stays in prose).
- [ ] **Step 4: Verify backend** Expected: all four pass.
- [ ] **Step 5: Diff scan** (Task 1 Step 6 checks)
- [ ] **Step 6: Commit** - `docs(retrieval): rewrite comments and docstrings to the new standard`

---

### Task 7: Answers & conversations slice

**Files:**
- Modify: `backend/app/answers/*.py` (4 files), `backend/app/conversations/*.py` (4 files), `backend/tests/answers/*.py`, `backend/tests/conversations/*.py`
- Modify: `web/src/features/chat/*.ts(x)` (4 files + tests)

**Interfaces:**
- Consumes: Task 1 style; retrieval from Task 6; providers from Task 5.
- Produces: corrected "S6 reranker" docstring in `tests/answers/test_answer_api.py:97`; collapse `conversations/service.py` ×3 `Read-only close` comment to once per file.

- [ ] **Step 1: Fix stale/wrong/duplicated text** - S6 to S7 in `test_answer_api.py:97`; deduplicate the read-only-close comment.
- [ ] **Step 2: Fill gaps** - `answers/prompt.py`, `answers/router.py` why-commentary; `ChatPanel`/`ChatPage` exports all already commented - verify `@param` lists added.
- [ ] **Step 3: Rewrite the rest of the slice to the standard**
- [ ] **Step 4: Verify backend** Expected: all four pass.
- [ ] **Step 5: Verify frontend** Expected: all four pass.
- [ ] **Step 6: Diff scan** (Task 1 Step 6 checks)
- [ ] **Step 7: Commit** - `docs(answers): rewrite comments and docstrings to the new standard`

---

### Task 8: Workers slice

**Files:**
- Modify: `backend/app/workers/celery_app.py`, `dispatcher.py`, `signals.py`, `tasks.py`, `__init__.py`, `backend/tests/workers/*.py`

**Interfaces:**
- Consumes: Task 1 style; ingestion tasks from Task 4.
- Produces: preserved retry/claim invariant comments in `dispatcher.py` (exemplar quality - keep nearly verbatim).

- [ ] **Step 1: Fix stale/wrong/duplicated text**
- [ ] **Step 2: Fill gaps** - `tasks.py`, `signals.py` why-commentary where missing.
- [ ] **Step 3: Rewrite the rest of the slice to the standard**
- [ ] **Step 4: Verify backend** Expected: all four pass.
- [ ] **Step 5: Diff scan** (Task 1 Step 6 checks)
- [ ] **Step 6: Commit** - `docs(workers): rewrite comments and docstrings to the new standard`

---

### Task 9: Frontend shell & theme slice

**Files:**
- Modify: `web/src/theme/themePrimitives.ts`, `web/src/theme/AppTheme.tsx`, `web/src/theme/ColorModeIconDropdown.tsx`, `web/src/theme/global.css`, `web/src/theme/customizations/*.ts(x)` (6 files), plus their tests
- Modify: `web/src/layouts/*.tsx` (11 files + tests), `web/src/features/landing/LandingPage.tsx` + test, `web/src/features/about/AboutPage.tsx` + test, `web/src/test/*.ts(x)` (7 files), `web/src/env.d.ts`

**Interfaces:**
- Consumes: Task 1 JSDoc style.
- Produces: documented design tokens (`brand`, `gray`, `green`, `orange`, `red`, `colorSchemes`, `typography`, `shape`, `shadows`) in `themePrimitives.ts`; commented component overrides in the 280-line `navigation.tsx` and 234-line `dataDisplay.tsx`.

- [ ] **Step 1: Fix stale/wrong/duplicated text** - the eslint-disable comment at `themePrimitives.ts:26` gets its period; duplicated `//` pairs between `AuthFrame.test.tsx`/`MarketingFrame.test.tsx` collapsed per file.
- [ ] **Step 2: Fill gaps** - the 9 theme tokens, `customizations/*.tsx` override files (currently 1 comment per 280 lines), `main.tsx` already handled in Task 1, `global.css`.
- [ ] **Step 3: Rewrite the rest of the slice to the standard**
- [ ] **Step 4: Verify frontend** Expected: all four pass. (No backend files in this slice.)
- [ ] **Step 5: Diff scan** (Task 1 Step 6 checks)
- [ ] **Step 6: Commit** - `docs(theme): rewrite comments and docstrings to the new standard`

---

### Task 10: E2E journey slice

**Files:**
- Modify: `web/e2e/journey.spec.ts`, `enforcement.spec.ts`, `marketing-navbar.spec.ts`, `venv.ts`

**Interfaces:**
- Consumes: Task 9 comment style; all feature slices' behavior (unchanged).
- Produces: `marketing-navbar.spec.ts` upgraded from 2 comments to full step narration matching `journey.spec.ts` quality; duplicated `// example.test is a special-use TLD` pair collapsed per file.

- [ ] **Step 1: Fix stale/wrong/duplicated text**
- [ ] **Step 2: Fill gaps** - narrate each e2e step's intent in `marketing-navbar.spec.ts` and any thin spots in `enforcement.spec.ts`.
- [ ] **Step 3: Rewrite the rest of the slice to the standard** (`venv.ts` multi-line JSDoc gets `@param` lists).
- [ ] **Step 4: Verify frontend** Expected: all four pass. (`npx playwright test` optional here; e2e requires browsers/services - not required since behavior is unchanged.)
- [ ] **Step 5: Diff scan** (Task 1 Step 6 checks)
- [ ] **Step 6: Commit** - `docs(e2e): rewrite comments and docstrings to the new standard`

---

### Task 11: Cross-cutting sweep and completion

**Files:**
- Modify: any file across the repo flagged below
- Modify: `docs/system-overview.md`, `docs/backlog.md`

**Interfaces:**
- Consumes: all prior tasks' output on branch `comment-docstring-rewrite`.
- Produces: frozen spec state, updated system overview, timestamped backlog entries for leftovers.

- [ ] **Step 1: Stale-reference audit**

Search the whole repo for `S6`, `S7`, `R2`, `R5`, `R6`, `U1`, `decision `, `spec 6`, `spec 8`, `Focus 4` in comments/docstrings; re-validate each against `docs/superpowers/specs/` and `docs/backlog.md`; correct or remove IDs that no longer help a reader.

- [ ] **Step 2: Standard-compliance sweep**

Spot-check every slice's files against the spec's standard: missing `:param:` lists, lowercase comment starts, comments ending without a period, restating-the-code comments, remaining verbatim duplicates within a file.

- [ ] **Step 3: Full verification**

Run backend `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest`; frontend `npm run lint`, `npx tsc -b`, `npm run test`, `npm run format:check`.
Expected: all pass.

- [ ] **Step 4: Update docs**

Update `docs/system-overview.md` to reflect the new comment/docstring standard state (per AGENTS.md). Add any leftover items to `docs/backlog.md` with a timestamped header and links to the relevant commits.

- [ ] **Step 5: Commit**

```bash
git commit -m "docs(sweep): validate stale references and update overview"
```

- [ ] **Step 6: Fresh-context review**

Dispatch a fresh-context review of the whole branch using **only** `opencode/mimo-v2.6-flash-free`; fix findings, one commit per concern.
