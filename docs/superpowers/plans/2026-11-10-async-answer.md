# Async `/answer` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/answer` an `async def` route whose LLM calls are awaited over `httpx.AsyncClient`, while every database call, including `retrieve()`, stays sync and runs in the threadpool.

**Architecture:** First, the LLM provider moves from per-request construction to one instance per app process, built in the lifespan and injected through a FastAPI dependency (still sync calls). Second, the `LLMProvider` protocol becomes async, and the answer route and service become `async def`, offloading each database step with `anyio.to_thread.run_sync`. Docs and the end-to-end check close the branch.

**Tech Stack:** Python 3.14, FastAPI 0.154, Starlette 1.9, anyio 4.15 (pytest plugin), httpx 0.28, sync SQLAlchemy 2.1 + psycopg 3, pytest, ruff, mypy strict; Playwright for the e2e journey. Worktree `async-answer`, branch `async-answer`.

**Spec:** `docs/superpowers/specs/2026-11-10-async-answer-design.md` - the plan argues from the spec; executors read both.

## Global Constraints

- Hybrid only: no `AsyncSession`, no async engine, no new database driver (spec decision 1).
- `/retrieve`, `retrieve()`, `app/conversations/`, `app/core/db.py`, every other route, and Celery code are not modified (spec decisions 2-3).
- Offloading uses `anyio.to_thread.run_sync(functools.partial(...))`, never Starlette's `run_in_threadpool` (spec decision 4), and never `abandon_on_cancel=True` (spec decision 8).
- One request's offloaded database steps run strictly one after another; no `gather` or task group around database work (spec decision 7).
- API contract, routing and fallback rules, status codes (401, 404, 422, 502), persisted rows, and the "no transaction open across an LLM call" invariant stay unchanged.
- No new dependencies: async tests use the `anyio` pytest plugin, `@pytest.mark.anyio`, asyncio backend.
- Coding rules (`AGENTS.md`): keyword-only parameters on our functions, docstrings with `:param:` lines on every function including private ones and test fakes, a blank line after every docstring, line length 110, comments capitalized and ending with a period, no em dashes, no `# type: ignore` unless necessary.
- Test docstrings use the one-line imperative "Check that..." voice.
- Commits: one concern per commit, conventional messages, no co-author trailer; untracked files flagged by a review get their own commit.
- Verification per task, from `backend/`: `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest`.
- Models (`AGENTS.md`): implementers GLM 5.3 (Kimi K3 when GLM 5.3 is stuck); reviews Kimi K3.1 Pro.

## Review Focus

1. **A request cancelled while `append_turn` runs** (client disconnect, server shutdown): the turn must commit fully or not at all, never halfway. Pinned by `test_cancellation_never_interrupts_the_append_commit` in Task 2.
2. **A startup check that refuses to boot:** no LLM provider is built, so nothing leaks or needs closing. Pinned by `test_failed_startup_check_builds_no_provider` in Task 1.
3. **One request's `Session` touched by two threads at once:** only code shape prevents it. Pinned by Task 2's review step (inspect `generate_answer` for any concurrent database work) and the sequential-invariant comment.
4. **Groq transport failures under `AsyncClient`** (connect timeout, non-2xx, malformed body): they must still become `LLMError` with the user-safe copy, and so a 502. Pinned by the converted `tests/providers/test_groq_llm.py` in Task 2, which keeps every existing failure case.
5. **The real served stack** (uvicorn process, real lifespan, browser): asking a question in the UI must still answer. Pinned by the Playwright journey in Task 4.

## Task DAG

Arrows mean "depends on". The chain is linear: Task 2 changes the interface Task 1 injects, and the docs describe the finished state. No two tasks can run in parallel.

```
1 (app-scoped provider) ──► 2 (async LLM + offloaded DB) ──► 3 (docs) ──► 4 (e2e + final review)
```

---

### Task 1: One LLM provider per app process

**Files:**
- Modify: `backend/app/providers/base.py` (`LLMProvider` protocol)
- Modify: `backend/app/providers/stub_llm.py`, `backend/app/providers/groq_llm.py`, `backend/app/providers/__init__.py` (docstring only)
- Modify: `backend/app/main.py` (lifespan)
- Create: `backend/app/answers/dependencies.py`
- Modify: `backend/app/answers/router.py`, `backend/app/answers/service.py`
- Modify: `backend/tests/conftest.py` (add `anyio_backend`), `backend/tests/fakes.py`
- Modify: `backend/tests/answers/test_service.py`, `backend/tests/answers/test_answer_api.py:243-260`, `backend/tests/providers/test_groq_llm.py`
- Create: `backend/tests/answers/test_llm_lifespan.py`

**Interfaces:**
- Consumes: the existing `get_llm_provider(*, settings: Settings) -> LLMProvider` factory, unchanged.
- Produces:
  - `LLMProvider.aclose(self) -> Awaitable[None]`, declared `async def aclose(self) -> None`.
  - `app.answers.dependencies.get_app_llm_provider(*, request: Request) -> LLMProvider`, declared `async def`, so FastAPI calls it without a thread hop.
  - `app.state.llm_provider: LLMProvider`, set by the lifespan.
  - `generate_answer(*, db: Session, provider: LLMProvider, project_id: UUID, user_id: UUID, params: AnswerIn, settings: Settings) -> Answer | None`. Still sync in this task.
  - `app.main` imports `get_llm_provider`, so tests can monkeypatch `app.main.get_llm_provider`.

- [ ] **Step 1: Add the `anyio_backend` fixture**

In `backend/tests/conftest.py`, add a session-scoped `anyio_backend` fixture returning `"asyncio"`, with a docstring saying the suite runs async tests on asyncio only.

- [ ] **Step 2: Write the failing lifespan tests** in `backend/tests/answers/test_llm_lifespan.py`

Both tests monkeypatch `app.main.SessionLocal` (as `tests/retrieval/test_startup_guard.py` does). They use a local fake `_ClosingLLMProvider` with `closed: bool = False` and an `async def aclose` that sets it to `True`.

```python
def test_lifespan_owns_one_llm_provider(*, engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _ClosingLLMProvider()
    monkeypatch.setattr("app.main.run_startup_checks", lambda *, db, embedding_provider: None)
    monkeypatch.setattr("app.main.get_llm_provider", lambda *, settings: fake)
    with TestClient(app):
        assert app.state.llm_provider is fake
        assert fake.closed is False
    assert fake.closed is True


def test_failed_startup_check_builds_no_provider(*, engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[object] = []
    # run_startup_checks raises RuntimeError("boom"); get_llm_provider appends to `built`.
    with pytest.raises(RuntimeError, match="boom"), TestClient(app):
        pass
    assert built == []
```

Write the lambdas as small named functions wherever a docstring is required.

- [ ] **Step 3: Write the failing Groq close test** in `backend/tests/providers/test_groq_llm.py`

Add `_RecordingTransport(httpx.MockTransport)`. It overrides both `close` and `aclose` to set `self.closed = True`, so the test still holds after Task 2 switches to `AsyncClient`. Add:

```python
@pytest.mark.anyio
async def test_aclose_closes_the_transport() -> None:
    transport = _RecordingTransport(_router_reply(content="{}"))
    provider = GroqLLMProvider(..., transport=transport)  # Same knobs as _provider().
    await provider.aclose()
    assert transport.closed is True
```

- [ ] **Step 4: Run the new tests and verify they fail**

Run: `pytest tests/answers/test_llm_lifespan.py tests/providers/test_groq_llm.py::test_aclose_closes_the_transport -v`
Expected: FAIL. `app.main` has no `get_llm_provider` attribute, `app.state` has no `llm_provider`, and `GroqLLMProvider` has no `aclose`.

- [ ] **Step 5: Implement `aclose` and the lifespan**

- `base.py`: add `async def aclose(self) -> None` to `LLMProvider`. Docstring: releases the provider's network resources; the app calls it once, at shutdown.
- `stub_llm.py`: a no-op `async def aclose`.
- `groq_llm.py`: `async def aclose` calls `self._client.close()` (the client is still sync in this task). Update the `__init__` docstring: one client serves the provider's whole lifetime, which is the app process.
- `main.py`:
  - Rename the lifespan parameter to `fastapi_app: FastAPI`.
  - After the startup checks, build `provider = get_llm_provider(settings=get_settings())` and store it on `fastapi_app.state.llm_provider`.
  - Then `try: yield` / `finally: await provider.aclose()`.
  - The provider is built after the checks on purpose, so a refused boot builds nothing.
  - Update the lifespan docstring.
- `providers/__init__.py`: the `get_llm_provider` docstring notes that the app lifespan calls it once per process.

- [ ] **Step 6: Inject the provider**

- Create `app/answers/dependencies.py` with `async def get_app_llm_provider(*, request: Request) -> LLMProvider`. It returns `request.app.state.llm_provider`, annotated through a typed local so mypy strict accepts the `Any`.
- `router.py`: add a `provider: LLMProvider = Depends(get_app_llm_provider)` parameter with a `:param:` line, and pass `provider=provider` to `generate_answer`.
- `service.py`: add the `provider` parameter, delete the `get_llm_provider(settings=settings)` call and its import, and add the `:param provider:` line.

- [ ] **Step 7: Move the tests off the monkeypatched factory**

- `tests/fakes.py`: `RecordingLLMProvider` and `RaisingLLMProvider` gain a no-op `async def aclose`.
- `tests/answers/test_service.py`:
  - `_answer` gains `provider: LLMProvider | None = None`, where `None` means `StubLLMProvider()`.
  - Every `monkeypatch.setattr("app.answers.service.get_llm_provider", ...)` becomes `provider=...` on the `_answer` or `generate_answer` call.
  - Drop the `monkeypatch` parameter and its `:param:` line from every test that no longer uses it.
  - The direct `generate_answer(...)` calls at lines 120, 470 and 517 pass `provider=StubLLMProvider()`, or their fake.
  - `TxnRecordingLLMProvider` gains `aclose`.
- `tests/answers/test_answer_api.py`: `test_llm_failure_maps_to_502_and_still_logs` sets `app.dependency_overrides[get_app_llm_provider]` to a named function returning `RaisingLLMProvider()`, and drops `monkeypatch`. The `client` fixture already clears overrides at teardown.

- [ ] **Step 8: Run the full verification**

Run from `backend/`: `ruff check .`, then `ruff format --check .`, then `mypy app tests`, then `pytest`.
Expected: all pass, including the 3 new tests and the 2 existing tests in `tests/retrieval/test_startup_guard.py`. `grep -r "answers.service.get_llm_provider" tests` returns nothing.

- [ ] **Step 9: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat(answers): build the LLM provider once per app process"
```

---

### Task 2: Async LLM calls and an async `/answer` with offloaded database steps

**Files:**
- Modify: `backend/app/providers/base.py`, `backend/app/providers/stub_llm.py`, `backend/app/providers/groq_llm.py`
- Modify: `backend/app/answers/service.py`, `backend/app/answers/router.py`
- Modify: `backend/tests/fakes.py`, `backend/tests/providers/test_stub_llm.py`, `backend/tests/providers/test_groq_llm.py`, `backend/tests/answers/test_service.py`
- Create: `backend/tests/answers/test_answer_concurrency.py`

**Interfaces:**
- Consumes: Task 1's `get_app_llm_provider`, `app.state.llm_provider`, `LLMProvider.aclose`, and the `generate_answer(*, db, provider, ...)` signature.
- Produces:
  - `LLMProvider.generate(...)` and `LLMProvider.route(...)` as `async def`, with the same parameters and return types as before.
  - `GroqLLMProvider(..., transport: httpx.AsyncBaseTransport | None = None)`.
  - `async def generate_answer(...) -> Answer | None`, with Task 1's parameters.
  - `async def answer_question(...)`.

- [ ] **Step 1: Write the failing concurrency test** in `backend/tests/answers/test_answer_concurrency.py`

The test needs a fake:
- `_BarrierLLMProvider(*, parties: int)`, constructed inside the async test, because `anyio.Event` needs a running loop.
- `route()` increments an arrival counter, sets an `anyio.Event` when the counter reaches `parties`, awaits the event, and then returns `RouteDecision(route="direct", rewritten_query=None)`.
- `generate()` returns `"direct answer"`, and `aclose()` does nothing.

```python
@pytest.mark.anyio
async def test_waiting_llm_calls_hold_no_threadpool_token(*, db_session: Session) -> None:
    owners = [register_user(db=db_session, email=f"conc-{n}@example.com", password="password123") for n in (1, 2)]
    provider = _BarrierLLMProvider(parties=2)
    # Override get_db to return db_session and get_app_llm_provider to return provider (named functions).
    limiter = anyio.to_thread.current_default_thread_limiter()
    original_tokens = limiter.total_tokens
    limiter.total_tokens = 1
    statuses: list[int] = []
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            with anyio.fail_after(5):
                async with anyio.create_task_group() as group:
                    for owner in owners:
                        group.start_soon(_ask, http, owner, statuses)  # Positional: anyio's start_soon.
    finally:
        limiter.total_tokens = original_tokens
        app.dependency_overrides.clear()
    assert statuses == [200, 200]
```

- `_ask(*, http, owner, statuses)` posts `{"query": "hello"}` to `/api/projects/{owner.project.id}/answer`, sends a bearer token from `create_access_token(user_id=owner.user.id, settings=get_settings())`, and appends the status code. `start_soon` takes only positional arguments, so pass it `functools.partial(_ask, http=..., owner=..., statuses=...)`.
- The module docstring explains why this proves the goal. With one threadpool token, a request that held a thread while waiting on the LLM would block the other request's auth dependency. The barrier would then never fill, and `fail_after` fires.

- [ ] **Step 2: Write the failing cancellation test** in `backend/tests/answers/test_service.py`

```python
@pytest.mark.anyio
async def test_cancellation_never_interrupts_the_append_commit(*, db_session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    # Seed a project and user; `started`/`release` are threading.Event objects.
    # Monkeypatch app.answers.service.append_turn with a wrapper: started.set(); release.wait(5); return real_append_turn(**kwargs).
    async with anyio.create_task_group() as group:
        group.start_soon(partial(_answer, db=db_session, provider=RecordingLLMProvider(answer="kept [1]",
            route_response=RouteDecision(route="direct", rewritten_query=None)), ...))
        await anyio.to_thread.run_sync(started.wait)
        group.cancel_scope.cancel()
        release.set()
    # Both turn messages (user + assistant) of the seeded user's conversation are committed.
    count = db_session.scalar(
        select(func.count()).select_from(ConversationMessage).join(Conversation)
        .where(Conversation.user_id == user.id)
    )
    assert count == 2
```

The wrapper and `_answer` get docstrings. The test docstring states the invariant (spec decision 8): anyio's default lets a running thread step finish, so a cancelled request still commits the whole turn.

- [ ] **Step 3: Run the new tests and verify they fail**

Run: `pytest tests/answers/test_answer_concurrency.py tests/answers/test_service.py::test_cancellation_never_interrupts_the_append_commit -v`
Expected: FAIL. The sync service calls `provider.route(...)` without awaiting it, so the concurrency test sees a `'coroutine' object has no attribute 'route'` error, and the cancellation test fails on `await` of a non-awaitable `_answer` result.

- [ ] **Step 4: Make the providers async**

- `base.py`: `async def generate`, `async def route`; the module docstring notes that `LLMProvider` is async while `Parser` and `EmbeddingProvider` stay sync.
- `stub_llm.py`: `async def generate` and `async def route`, same outputs.
- `groq_llm.py`:
  - `httpx.AsyncClient`, and the `transport: httpx.AsyncBaseTransport | None` annotation.
  - `async def _complete` with `await self._client.post(...)`.
  - `async def generate` and `async def route`.
  - `aclose` becomes `await self._client.aclose()`.
  - Parsing, error mapping, budgets and timeouts are unchanged.
- `tests/fakes.py`: async `generate` and `route` on both fakes.

- [ ] **Step 5: Make the service async and offload the database steps** in `backend/app/answers/service.py`

- Add a frozen dataclass `_TurnContext` with fields `conversation: Conversation`, `history: list[ChatMessage]` and `gathered: list[ConversationMessageChunk]`.
- Add the sync helper `_load_turn_context(*, db: Session, project_id: UUID, user_id: UUID, conversation_id: UUID | None, settings: Settings) -> _TurnContext | None`. It moves today's lines 121-133 unchanged: resolve, then load history and gather snapshots when the id is set.
- `generate_answer` becomes `async def` and runs the steps in spec section 4 order:
  - `await anyio.to_thread.run_sync(partial(_load_turn_context, ...))`.
  - `await provider.route(...)`.
  - `await provider.generate(...)` on each path.
  - `await anyio.to_thread.run_sync(partial(retrieve, ...))`.
  - `await anyio.to_thread.run_sync(partial(append_turn, ...))` at both call sites.
- One comment at the first offload states the invariant: these steps share one `Session` and must run one after another, never concurrently.

- [ ] **Step 6: Make the route async** in `backend/app/answers/router.py`

`async def answer_question`: run the project lookup through `await anyio.to_thread.run_sync(partial(get_project_visible_to_user, db=db, user=user, project_id=project_id))`, then `answer = await generate_answer(...)`. Error mapping is unchanged.

- [ ] **Step 7: Convert the remaining tests to async**

- `tests/providers/test_stub_llm.py` and every test in `tests/providers/test_groq_llm.py`: `@pytest.mark.anyio async def`, with `await` on each `generate` and `route` call, including inside `pytest.raises`. Keep every existing case and assertion.
- `tests/answers/test_service.py`:
  - `_answer` and every test that calls it or `generate_answer` become async.
  - `TxnRecordingLLMProvider`'s methods become `async def`.
  - Sync seed and `retrieve` calls stay plain calls inside the async tests.
- `tests/answers/test_answer_api.py` needs no change beyond Task 1.

- [ ] **Step 8: Run the full verification**

Run from `backend/`: `ruff check .`, then `ruff format --check .`, then `mypy app tests`, then `pytest`.
Expected: all pass, including the two new tests and `test_llm_calls_run_with_no_open_transaction`.
Then check the timing-sensitive tests for flakiness: `for ($i = 0; $i -lt 5; $i++) { pytest tests/answers/test_answer_concurrency.py "tests/answers/test_service.py::test_cancellation_never_interrupts_the_append_commit" -q }`.
Expected: 5 passing runs.

- [ ] **Step 9: Review the session invariant** (Review Focus 3)

Read the final `generate_answer` and `answer_question`. Confirm that every `to_thread.run_sync` is awaited before the next database step starts, and that there is no `gather`, task group, or `abandon_on_cancel` on this path.

- [ ] **Step 10: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat(answers): await LLM calls and offload database work from an async /answer"
```

---

### Task 3: Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-10-06-roadmap.md:121`
- Modify: `docs/2026-10-19-system-overview.md` (the `#### api` section near line 71, and "Runtime flow of one question" near lines 145-171)
- Modify: `docs/backlog.md` (S5 section line 349, plus a new dated section)
- Modify: `docs/superpowers/specs/2026-11-10-async-answer-design.md` (status line)

**Interfaces:**
- Consumes: the commit hashes of Tasks 1 and 2 (`git log --oneline -3`).
- Produces: nothing code-facing.

- [ ] **Step 1: Roadmap**

Line 121 keeps the "Sync SQLAlchemy 2.0" bullet and appends one sentence: `/answer` is `async def` (2026-11-10); its database work runs in the threadpool and its LLM calls are awaited, while every other route stays sync.

- [ ] **Step 2: System overview**

- The `#### api` paragraph: add that `/answer` is the one async route. Its LLM provider is built once per process at startup and closed at shutdown, and its database steps run in the threadpool, so a waiting answer holds no thread.
- "Runtime flow of one question", step 1: say that the reads run in the threadpool.
- Step 2: say that the router call is awaited.

- [ ] **Step 3: Backlog**

- Append to line 349's item: `Resolved on 2026-11-10 in async-answer (<Task 1 hash>): the lifespan builds one provider per process and closes it at shutdown.`
- Add the section `## 2026-11-10 - async /answer (branch async-answer) follow-ups` with two items, each linking `<Task 2 hash>`:
  - Make the remote embedding and rerank calls async when a network provider or the S7 reranker arrives (spec decision 2).
  - Nothing limits concurrent in-flight answers. Their database steps still share the 40-token threadpool and the 15-connection pool (30s pool timeout), and the LLM's rate limits apply (spec section 7).
- Do not touch the line 372 deadline item; it stays open.

- [ ] **Step 4: Spec status**

Set the status line to `Implemented 2026-11-10 on the async-answer branch (<first hash>..<last hash>), under ../plans/2026-11-10-async-answer.md. Frozen: decisions below are as built.`

- [ ] **Step 5: Check for em dashes and commit**

Run: `git diff --name-only | ForEach-Object { Select-String -Path $_ -Pattern "\u2014" }` (the .NET regex escape for the em dash).
Expected: no output.

```bash
git add docs
git commit -m "docs: record the async /answer state"
```

---

### Task 4: End-to-end check and final review

**Files:** none modified unless a check fails.

**Interfaces:**
- Consumes: the finished branch.
- Produces: the verification evidence for the handoff.

- [ ] **Step 1: Backend suite on the final tree**

Run from `backend/`: `ruff check .`, then `ruff format --check .`, then `mypy app tests`, then `pytest`.
Expected: all pass.

- [ ] **Step 2: Playwright journey** (Review Focus 5)

Prerequisites: local Postgres on 5432 and RabbitMQ on 5672, as `web/playwright.config.ts` expects.
Run from `web/`: `npx playwright test e2e/journey.spec.ts`.
Expected: the journey passes. The question step gets the stub answer through a real uvicorn process, whose lifespan built the provider. If the infrastructure is unavailable, report that explicitly; do not count the step as passed.

- [ ] **Step 3: Whole-branch review**

Dispatch a fresh-context reviewer (Kimi K3.1 Pro) over `master..async-answer` against the spec and this plan's Review Focus. Fix findings in dedicated commits, and record any accepted residuals in the Task 3 backlog section.
