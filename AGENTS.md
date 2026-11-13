# Coding rules

## Python

- Line length is 110, enforced by ruff (`backend/pyproject.toml`)
- Every module, class, and function has a docstring, enforced by ruff pydocstyle rules (alembic scripts are exempt)
- Private functions and methods (leading underscore) have docstrings too; ruff only checks public definitions, so this is enforced by `tests/test_style.py`
- Every docstring is followed by a blank line before the next statement, enforced by `tests/test_style.py`
- If function arguments do not fit on one line, split them onto separate lines, one per line, enforced by `ruff format`
- All parameters of our functions are keyword-only (`def f(*, a, b)`), so every call passes arguments by name. Enforced by ruff `PLR0917` with `max-positional-args = 0`; Use positional arguments for third-party calls too
- Do not silence type errors with `# type: ignore` unless necessary
- Prefer precise return types and parameter annotations

## Model selection
This is the list of allowed models weaker to stronger: 
  1. GLM 5.3 flash 
  2. GLM 5.3
  3. Kimi K3 
  4. Kimi K3.1 Pro
  5. Claude Opus 5.5
Use the strongest model for fresh context reviews. Use it for specification writing.  

## Generic 
- In every detailed plan you create, add a DAG of the tasks so that unrelated tasks could be done in parallel if necessary
- When a specification has been implemented it should freeze. The source of truth is the roadmap specification
- After a task is completed, update the docs/system-overview.md file to reflect the new state  
- Any test longer than 5 seconds should be marked as long

## Asynchronous Background tasks

For every asynchronous background task, answer two questions:
1. What happens if the same task runs again after partial progress or success?
2. What happens if two workers run it at the same time?

Ensure retries preserve completed work and concurrent runs leave the system
in a consistent state. If a worker claims a task, explain how another worker
can recover it after a crash. Mark the task complete only after its results
are durable. Document any external calls that may repeat.

Every asynchronous task that claims work beyond a single database transaction
must implement the lease pattern, so orphaned or stuck jobs recover on their own:
- An `attempt` counter that the claim increments and every later write checks
  (a fencing token), so a stale worker's writes match nothing
- A `lease_expires_at` deadline that the worker renews by heartbeat while it
  runs, capped so a hung worker cannot renew forever, and that is also set while
  the job waits to be picked up
- A sweeper that finds expired leases and re-drives the job, or fails it with a
  user-safe error after a maximum number of attempts

Work that runs entirely inside one transaction under row locks (like the outbox
dispatcher's `SKIP LOCKED` batch) needs no lease: a crash rolls it back and
releases the locks. Reference design:
`docs/superpowers/specs/2026-11-13-ingestion-run-leases-design.md`.

## Comments

- Comments start with a capital letter and end with a dot
- Do not write comments that merely restate the code
- Comments should be simple and clear, explaining why, constraints, invariants, or non-obvious behavior
- Keep docstrings focused on public API behavior and use clear and simple explanations. Docstrings are for users, comments for developers
- Docstrings should have :param, :return and :raises explanations. Use the Sphinx style for these directives.

## Git workflow

- All tasks should be done in a worktree so that parallel tasks can be worked on without interference
- Never commit on a detached HEAD: use the worktree's existing branch, or create one named after the worktree (`git switch -c <task-name>`) before the first commit
- All tasks should undergo a fresh-context review at the end except if they have been completed through the superpowers skillset which already has a review built in
- Any backlog items remaining after the completion of a task, should be added to `docs/backlog.md` with a timestamped header, and a link to the relevant commit(s)
- One concern per commit
- When a review flags untracked files, give each its own dedicated commit instead of attaching it to a fix

## Verification

Before finishing a Python change, run:

    ruff check .
    ruff format --check .
    mypy app tests
    pytest

Small changes may iterate with `pytest -m "not long"` (the normal suite, without
the tests that measure over 5 seconds); the full `pytest` above must still pass
before a task is done.

A task is not complete while any of these fail because of the change
