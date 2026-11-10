# Async `/answer` - Design

Date: 2026-11-10
Status: Implemented 2026-11-10 on the `async-answer` branch (`c5f454a`..`5790200`),
under `../plans/2026-11-10-async-answer.md`. Frozen: decisions below are as built.
Source of truth: `2026-10-06-roadmap.md` (the "slices spec"). This document supersedes S5
decision 7's "sync `generate`" clause (`2026-10-20-s5-answer-chat-design.md`) and S5/S6's
per-request `get_llm_provider` call inside the answer service. Every other S5/S6 decision
stands unchanged; both specs stay frozen.

## 1. Context

`POST /api/projects/{project_id}/answer` is a sync `def` route, so FastAPI runs the whole request
in its threadpool. The request makes up to two sequential remote LLM calls (router, then
generate), bounded at 10s and 30s, and each one holds a threadpool thread while it waits on the
network. The api runs as one uvicorn process with anyio's default limit of 40 threadpool tokens,
and every sync route and sync dependency in the app (auth, login, `/api/health`, uploads,
`/retrieve`) shares those tokens. Around 40 slow answers in flight therefore stall the whole API.

The database work on this path is short and already closes its transaction before any LLM call
(S5 decision 10, S6 decision 14), so the database is not the bottleneck: the waiting threads are.

## 2. Goal and success criteria

The goal is concurrency, not per-request latency: an `/answer` request waiting on the LLM must not
hold a threadpool thread, so slow answers cannot starve the rest of the API. A single answer gets
no faster, and the default stub LLM shows no visible difference.

Done when:

- `/answer` is `async def` and both LLM calls are awaited over `httpx.AsyncClient`.
- All database work on the path, including `retrieve()`, still runs sync, in the threadpool.
- A regression test proves two `/answer` requests can both be waiting on the LLM while the
  threadpool has a single token (section 6).
- The API contract, routing and fallback rules, status codes (401, 404, 422, 502), persisted rows,
  and the "no transaction open across an LLM call" invariant are unchanged.

## 3. Decisions (2026-11-10 design round, user-approved)

1. **Hybrid, not full async.** The `/answer` route and the answer service become `async def`;
   the LLM provider becomes async; every database call stays sync SQLAlchemy and is offloaded to
   the threadpool. The slices spec's "Sync SQLAlchemy 2.0" decision stands. Rejected: async
   SQLAlchemy (`AsyncSession`). Database work takes milliseconds and the 15-connection pool, not
   the threads, caps it; async sessions would also duplicate the models' session story with
   Celery, bring lazy-loading pitfalls, and force a rewrite of the shared test session fixture
   and roughly 100 tests.
2. **`/retrieve` and `retrieve()` stay sync.** The `/retrieve` route stays `def`. Its embedding is
   a local CPU hash today, with no network wait to gain from. When a network embedding provider
   or the S7 reranker arrives, that one remote call becomes async; the rest of `retrieve()` stays
   sync (backlog follow-up, section 8).
3. **Every other route and Celery are untouched.** Sync dependencies (`get_current_user`,
   `get_db`, `get_settings`) stay sync; FastAPI already runs them in the threadpool.
4. **Offloading uses `anyio.to_thread.run_sync` with `functools.partial`.** Not Starlette's
   `run_in_threadpool`, so the answer service imports no web framework. Both draw on the same
   default limiter.
5. **The `LLMProvider` protocol becomes async:** `async def generate`, `async def route`, and a new
   `async def aclose() -> None`. `ChatMessage`, `RouteDecision`, `LLMError` and its user-safe
   message contract are unchanged.
6. **One LLM provider per app process.** The lifespan builds it once through the existing
   `get_llm_provider(settings=...)` factory, stores it on `app.state.llm_provider`, and awaits its
   `aclose()` on shutdown. A FastAPI dependency hands it to the route, and the route passes it to
   `generate_answer(*, provider, ...)`. This closes the backlog item "fresh `httpx.Client` per
   answer request, never closed" and lets connections pool across requests. Rejected: a
   module-level shared `AsyncClient` behind the per-request factory. An `AsyncClient` belongs to
   the event loop that first used it, each `TestClient` context starts a new loop, and a global
   client is hidden state that is awkward to close.
7. **The request's `Session` crosses threads sequentially, never concurrently.** The offloaded
   steps of one request run strictly one after another on the same `Session`. The answer service
   must never run two of them in parallel (no `gather`, no task group around database work); a
   code comment at the orchestration states this invariant.
8. **Cancellation never interrupts a commit.** If the request is cancelled while awaiting an LLM
   call, nothing has been persisted yet. If it is cancelled while a threadpool step runs, anyio's
   default (`abandon_on_cancel=False`) lets the step finish, so an `append_turn` commit is never
   cut off halfway.
9. **Out of scope:** streaming (the S5 rejection stands), a total per-request deadline (backlog
   item stays open), uvicorn worker count or threadpool limit changes, retries, and any change to
   the `/retrieve` endpoint.

## 4. Request flow

`answer_question` becomes `async def` and gains a `provider: LLMProvider` dependency. In order:

1. **Auth and session** (sync dependencies, run by FastAPI in the threadpool): unchanged.
2. **Project lookup** (threadpool): `get_project_visible_to_user`; `None` raises 404 as today.
3. **`await generate_answer(...)`**, which runs:
   1. **Turn context** (threadpool, one hop): a new private sync helper runs
      `resolve_conversation`, then, when the conversation has an id, `load_history` and
      `gather_snapshots`. It returns `None` for a foreign `conversation_id` (the router's 404) or
      the conversation, history, and gathered snapshots. Every read commits before it returns, as
      today.
   2. **Router call** (async): `await provider.route(...)`; an `LLMError` falls back to
      `retrieve` with the raw question, as today.
   3. **The chosen path:**
      - `direct` and `reuse`: `await provider.generate(...)`.
      - `retrieve`: the existing sync `retrieve(...)` (threadpool), then, if it returned chunks,
        `await provider.generate(...)`. An empty result takes the canned-answer path with no LLM
        call, as today.
   4. **Persist** (threadpool): `append_turn(...)`, unchanged.
4. **Error mapping** (unchanged): `LLMError` becomes 502 with its user-safe message; a `None`
   result becomes 404 "conversation not found".

## 5. Components

| File | Change |
|---|---|
| `app/providers/base.py` | `LLMProvider`: async `generate` and `route`, new async `aclose`; module docstring notes the async interface. |
| `app/providers/groq_llm.py` | `httpx.AsyncClient`; `transport: httpx.AsyncBaseTransport \| None`; async `_complete`, `generate`, `route`; `aclose` closes the client. Parsing, error mapping, budgets, and timeouts unchanged. |
| `app/providers/stub_llm.py` | Async `generate` and `route`; no-op `aclose`. Same deterministic outputs. |
| `app/providers/__init__.py` | `get_llm_provider` unchanged in signature; docstring notes it is called once per process by the lifespan. |
| `app/main.py` | Lifespan builds the provider after the startup checks, stores it on `app.state.llm_provider`, and awaits `aclose()` in a `finally` after `yield`. |
| `app/answers/dependencies.py` (new) | `get_app_llm_provider(*, request: Request) -> LLMProvider` returns `request.app.state.llm_provider`. |
| `app/answers/router.py` | `async def answer_question`; provider dependency; project lookup offloaded. |
| `app/answers/service.py` | `async def generate_answer(*, db, provider, project_id, user_id, params, settings)`; private sync turn-context helper; database steps offloaded per section 4; the sequential-session comment (decision 7). |

`app/retrieval/`, `app/conversations/`, `app/core/db.py`, and Celery code are not modified.

## 6. Testing

The `anyio` pytest plugin ships with the installed `anyio`, so no new dependency is added. Async
tests use `@pytest.mark.anyio` on the asyncio backend.

- **Fakes** (`tests/fakes.py`): `RecordingLLMProvider` and `RaisingLLMProvider` get async
  `generate`/`route` and a no-op `aclose`.
- **Service tests** (`tests/answers/test_service.py`): async tests that call
  `await generate_answer(provider=fake, ...)` directly; the
  `monkeypatch.setattr("app.answers.service.get_llm_provider", ...)` calls go away. Every current
  assertion stays, including `test_llm_calls_run_with_no_open_transaction`, whose recording
  provider becomes async.
- **API tests** (`tests/answers/test_answer_api.py`): keep the sync `TestClient`; provider
  overrides go through `app.dependency_overrides[get_app_llm_provider]`. The 502 and
  router-fallback cases stay covered.
- **Groq tests** (`tests/providers/test_groq_llm.py`): async, over `httpx.MockTransport` (which
  serves `AsyncClient` too). New: `aclose()` closes the client.
- **Stub tests** (`tests/providers/test_stub_llm.py`): async.
- **Lifespan test (new):** startup stores the factory-built provider on `app.state.llm_provider`;
  shutdown awaits its `aclose()`.
- **Concurrency regression test (new, the key test):**
  - The test sets anyio's default thread limiter to one token, restoring it afterwards.
  - It sends two concurrent `/answer` requests through `httpx.AsyncClient` over
    `httpx.ASGITransport`, for two different users, each routed `direct` by the fake provider.
  - The fake's `route()` waits until both requests are inside it, under `anyio.fail_after(5)`.
  - With sync LLM calls, the first request would hold the only token and the test would time
    out; with async calls both proceed.
  - The single token also serializes the two requests' threadpool steps on the shared test
    session, which keeps the test safe.

Verification before completion: `ruff check .`, `ruff format --check .`, `mypy app tests`,
`pytest`, and the Playwright journey `web/e2e/journey.spec.ts` (which asks a question through the
UI on the stub LLM) as the end-to-end check.

## 7. Risks

- **Unbounded in-flight answers.** Waiting answers no longer consume threadpool tokens, so more of
  them can be in flight at once. Their database steps still go through the 40-token threadpool and
  the 15-connection pool (30s pool timeout), and the upstream LLM's rate limits still apply. No
  limit is added this round; a load symptom here is a follow-up, not a blocker.
- **Session thread hopping.** Safe only while decision 7 holds; the code comment and the
  sequential orchestration are the guard.

## 8. Documentation updates

- `docs/superpowers/specs/2026-10-06-roadmap.md` (line 121): keep "Sync SQLAlchemy 2.0" and add
  that `/answer` is `async def`, with database work offloaded to the threadpool and async LLM
  calls.
- `docs/2026-10-19-system-overview.md`: the "Runtime flow of one question" and the api process
  description gain the async route, the threadpool offloading, and the app-scoped LLM provider.
- `docs/backlog.md`:
  - Mark "fresh `httpx.Client` per answer request, never closed" resolved, linking the commit.
  - Add: make the remote embedding and rerank calls async when a network provider or the S7
    reranker arrives (decision 2).
  - Add: no limit on concurrent in-flight answers (section 7).
  - The total per-request deadline item stays open.
- Provider and answer-module docstrings per section 5.
