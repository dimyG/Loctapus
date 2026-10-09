# Coding rules

## Python

- Line length is 110, enforced by ruff (`backend/pyproject.toml`).
- Every module, class, and function has a docstring, enforced by ruff pydocstyle rules (alembic scripts are exempt).
- Private functions and methods (leading underscore) have docstrings too; ruff only checks public definitions, so this is enforced by `tests/test_style.py`.
- Every docstring is followed by a blank line before the next statement, enforced by `tests/test_style.py`.
- If function arguments do not fit on one line, split them onto separate lines, one per line, enforced by `ruff format`.
- All parameters of our functions are keyword-only (`def f(*, a, b)`), so every call passes arguments by name. Enforced by ruff `PLR0917` with `max-positional-args = 0`; mypy also rejects positional calls at compile time, and Python at runtime. Third-party calls are outside the rule.
- Do not silence type errors with `# type: ignore` unless necessary.
- Prefer precise return types and parameter annotations.

## Comments

- Comments start with a capital letter and end with a dot.
- Do not write comments that merely restate the code.
- Comments should explain why, constraints, invariants, or non-obvious behavior.
- Avoid comments describing implementation details that are obvious from names.
- Keep docstrings focused on public API behavior. Docstrings are for users, comments for developers.

## FastAPI Structure

- Routers handle HTTP concerns only.
- Business logic belongs in `service.py`.
- SQLAlchemy models belong in `models.py`.
- Pydantic request/response models belong in `schemas.py`.
- Database access should not leak into unrelated layers.

## Git workflow

- All tasks should be done in a worktree so that parallel tasks can be worked on without interference.
- All tasks should undergo a fresh-context review at the end except if they have been completed through the superpowers skillset which already has a review built in.
- Any backlog items remaining after the completion of a task, should be added to `docs/superpowers/backlog.md` with a timestamped header, and a link to the relevant commit(s).
- One concern per commit.
- When a review flags untracked files, give each its own dedicated commit instead of attaching it to a fix.

## Verification

Before finishing a Python change, run:

    ruff check .
    mypy app tests
    pytest

A task is not complete while any of these fail because of the change.
