# Comment and docstring rewrite - design specification

Date: 2026-11-09
Status: approved design, awaiting spec review
Branch: `comment-docstring-rewrite` (worktree `comment-docstring-rewrite`)

## Intent

Raise every docstring and comment in the Python backend and the React frontend to one clear standard: simple, concise, and readable by a junior developer. Each comment carries the high-level reason a thing exists, plus the details a reader needs to understand the whole picture. The pass is a **full rewrite of everything** (not a targeted fix-up): every existing docstring and comment is re-examined and rewritten to the standard, and new comments are added where the code would otherwise leave a junior developer lost.

Success criteria:

- Every Python function and method has a docstring with a Sphinx-style parameter list; every frontend export has a JSDoc comment with `@param` lines where it takes parameters.
- No stale, duplicated, or restating-the-code comments remain.
- The diff touches only comments and docstrings - zero behavior changes.
- After every backend slice: `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest` (run in `backend/`). After every frontend slice: `npm run lint`, `npm run test`, `npx tsc -b` (run in `web/`). All must pass.

## Model constraint (explicit user instruction)

**All work on this task - implementation slices, subagents, and the final fresh-context review - uses only the model `opencode/mimo-v2.6-flash-free` (MiMo V2.6 Flash Free).** No other model is permitted for any part of this task, including the end-of-task review. This overrides the model-selection list in `AGENTS.md` for this task only.

## Scope

- Python backend: `backend/app` (63 files), `backend/tests` (61 files), `backend/alembic` (8 files), `backend/scripts` (4 files). `__pycache__` excluded.
- React frontend: `web/src` (100 ts/tsx files), `web/e2e` (4 files).
- Out of scope: no lint/config changes (comment quality is convention-only, as agreed), no code/behavior changes, no new features.

## The standard

### Core principle

Every comment answers a junior developer's question before they have to ask it - why does this exist, what invariant does it protect, what happens if I change it - using the fewest words that still give the full picture.

### Python docstrings

Existing ruff pydocstyle rules and `tests/test_style.py` checks stay as they are (docstring on every module/class/function including private ones, blank line after every docstring, line length 110).

- **Summary line:** a complete sentence, capitalized, ending with a period, never starting with the function name ("Create a project..." not "create_project creates...").
- **Parameter list (new):** every function or method that takes parameters gets one `:param name:` line per parameter, directly after the summary (blank line between summary and list). No `:type:` lines - type information lives in the signature. All parameters are keyword-only (`PLR0917`), so the list mirrors the named parameters exactly.
- **Multi-line detail:** only when the summary plus list cannot hold the whole picture - then the details a reader needs (constraints, edge cases, tie-breaking, failure modes) go in a short paragraph between the summary and the list. No more.
- **Functions with no parameters** keep a plain one-line docstring; no empty parameter list.
- **Return values:** no `:return:`/`:rtype:` requirement; if a return value is non-obvious it is mentioned in the summary prose.
- **Test docstrings:** imperative "Check that..." voice, one line, naming the behavior verified (this unifies the current 285/48 split in favor of the majority imperative voice).
- **Module docstrings:** state the module's role in one short paragraph, plus the one non-obvious boundary rule (like `pipeline.py`'s "no SQLAlchemy here").

Target shape:

```python
def fuse_rrf(*, vector, fts, rrf_k):
    """Fuse both legs' rank-ordered candidates with reciprocal rank fusion.

    RRF uses ranks only, so the legs' raw scores never meet each other.

    :param vector: Rank-ordered candidates from the vector leg, rank 1 first.
    :param fts: Rank-ordered candidates from the full-text leg, rank 1 first.
    :param rrf_k: Smoothing constant; larger values flatten rank differences.
    """
```

Note: this grows most of the current ~754 one-line docstrings into summary + list. That is expected and intentional - uniformity is the goal.

### Inline `#` comments (Python)

- Capitalized start, ends with a period, explains why / constraint / invariant / non-obvious behavior - never restates the code.
- Existing good comments stay nearly verbatim; wording is rewritten only where the comment is stale, duplicated, vague, or could mislead.

### Frontend (TypeScript/React)

- `/** ... */` JSDoc above every export (functions, components, hooks, types, interfaces, constants): one-sentence purpose, then `@param {type} name - description` lines for parameters (native JSDoc syntax, mirroring the Sphinx rule).
- `//` inline why-comments follow the same capitalized / ends-with-period / never-restates rule.
- Every export gets a preceding comment (currently 22 exported consts/types lack one).

### Duplication rule

A comment repeated three or more times stays at most once per file, where it is most load-bearing; elsewhere it is dropped if the context makes it obvious, or replaced by a short pointer. Never four verbatim copies (the worst current case: `app/ingestion/service.py`, four copies of the same connection-failure comment).

### Stale references

Spec and slice IDs in comments (`S6`, `R2`, `R5`, `U1`, `decision 6`, `spec 6.1`, `Focus 4`, ...) are re-validated against the current specs during the rewrite. A comment referencing a moved or renamed artifact is corrected; the ID is removed entirely when it no longer helps a reader.

### Hard rules (unchanged)

- No em dashes anywhere.
- Diff touches only comments and docstrings; executable lines never change.
- Where a comment disagrees with the code, the comment is rewritten to describe what the code actually does; the underlying discrepancy stays in `docs/backlog.md`.

## Slice decomposition

Each slice is one vertical of the system: backend package(s) + their tests + the frontend feature(s) that consume them + related e2e. A writer inside a slice sees the full picture for that concern.

| # | Slice | Backend | Frontend / e2e |
|---|-------|---------|----------------|
| 1 | Core & bootstrap | `app/core`, `app/main.py`, `app/models.py`, `alembic/` (incl. `env.py`), `scripts/`, `tests/core`, `tests/test_config.py`, `tests/test_alembic.py`, `tests/test_style.py`, `tests/conftest.py`, `tests/__init__.py` | `web/src/app` (api, store, hooks, routes, boot), `web/src/main.tsx` |
| 2 | Identity & auth | `app/identity`, `tests/identity` | `features/auth`, `lib/tokenStorage`, `RequireAuth` |
| 3 | Projects & workspaces | `app/projects`, `tests/projects` | `features/projects`, `features/workspaces` |
| 4 | Sources, uploads & ingestion | `app/sources`, `app/ingestion`, `app/storage`, `app/outbox`, `tests/sources`, `tests/ingestion`, `tests/storage`, `tests/outbox` | `features/sources`, `features/uploads` |
| 5 | Providers | `app/providers`, `tests/providers` | - |
| 6 | Retrieval | `app/retrieval`, `tests/retrieval` | - |
| 7 | Answers & conversations | `app/answers`, `app/conversations`, `tests/answers`, `tests/conversations` | `features/chat` |
| 8 | Workers | `app/workers`, `tests/workers` | - |
| 9 | Frontend shell & theme | - | `theme/`, `layouts/`, `features/landing`, `features/about`, `test/` infra |
| 10 | E2E journey | - | `e2e/` (journey, enforcement, marketing-navbar, venv) |
| 11 | Cross-cutting sweep | Stale-reference audit (S6 to S7, R-ids, decisions) across everything | same, plus `docs/system-overview.md` update, `docs/backlog.md` links |

### DAG

Arrows mean depends on; sibling tracks can run in parallel.

```
1 ──► 2 ──► 3 ──► 4 ──► 6 ──► 7
│            │     │            │
│            │     └──► 8       │
│            │                  │
└──► 5 ──────┴── (5 free after 1)│
└──► 9 ──────────────────────► 10 ──► 11
```

- Slice 1 is the root: it establishes the standard's applied examples for the rest.
- 2 to 4 is the main backend chain (auth gates projects, projects own sources/ingestion).
- Slice 5 (providers) is free-standing after 1; slice 6 needs 4's ingestion context; slice 7 needs 6; slice 8 needs 4's task context.
- 9 to 10 is the frontend-only track; slice 11 runs last and touches everything.

## Per-slice workflow

1. Fix stale/wrong text first (known cases below).
2. Fill gaps: add missing docstrings/params/comments.
3. Rewrite the rest of the slice's text to the standard.
4. Verify: backend slices run `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest` in `backend/`; frontend slices run `npm run lint`, `npm run test`, `npx tsc -b` in `web/`.
5. Manual `git diff` scan confirming the diff is comments/docstrings only.
6. Commit - one concern per commit, `docs(<scope>): ...` message, no co-author trailer; untracked files get their own dedicated commit.

## Known special cases

- `backend/app/identity/service.py:72`: the comment claims a conflict target (`jti` primary key) that the code does not pass to `on_conflict_do_nothing()`. Rewrite the comment to describe actual behavior; keep the existing `docs/backlog.md` entry about the mismatch (slice 2).
- Three comments reference the "S6 reranker" though the feature moved to S7: `app/retrieval/schemas.py:34`, `tests/answers/test_answer_api.py:97`, `tests/retrieval/test_retrieve_api.py:94`. Correct or drop the ID (slices 6, 7, 11).
- `app/providers/__init__.py`: three factories carry an identical triplicated docstring; each gets its own accurate summary and parameter list (slice 5).
- ~20 duplicated backend comment groups and ~22 duplicated frontend comment pairs: collapse per the duplication rule.
- `web/src/theme/` is the weakest area (280-line files with one comment, 9 undocumented design tokens): filled in slice 9.
- Six frontend files have zero comments; large backend routers/security/base modules lean 100% on docstrings with no inline why-commentary: filled in their slices.
- `backend/alembic/env.py` is the only Python file without a module docstring (pydocstyle-exempt): add one in slice 1.
- `docs/backlog.md:580-585` already records the identity conflict-target mismatch; after slice 2 rewrites the comment, confirm the backlog entry still matches reality.

## Completion

- Fresh-context review of the whole branch, run with `opencode/mimo-v2.6-flash-free` only (per the model constraint above).
- Full verification run on the final state (all six commands).
- Update `docs/system-overview.md` to reflect the new state.
- Any leftover items go to `docs/backlog.md` with a timestamped header and links to the relevant commits.
- Once implemented, this specification freezes; `docs/backlog.md` becomes the source of truth for follow-ups.
