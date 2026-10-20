# S5 `/answer` + Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `POST /api/projects/{project_id}/answer` (retrieval in-process, grounded prompt, LLM provider layer with a stub and a Groq client) plus the project page's Ask/Documents tabs with the chat panel, so a question typed in the browser returns an answer grounded in cited chunks.

**Architecture:** A new `app/answers/` package sits on top of `app/retrieval` and never the reverse: the service calls `retrieve()` as a Python function, short-circuits an empty index, builds the numbered prompt, and calls the provider. The LLM joins the existing providers pattern (`LLMProvider` Protocol, `LLMError`, stub, `get_llm_provider` factory); Groq runs over httpx against the OpenAI-compatible `/chat/completions` endpoint. The frontend adds an RTK Query mutation and a `ChatPanel` mounted inside a two-tab `ProjectPage` (both panels stay mounted so the thread survives tab switches and uploads polling never stops).

**Tech Stack:** FastAPI, pydantic v2, httpx (runtime dependency), SQLAlchemy 2.0 sessions, RTK Query, MUI Tabs/Accordion, vitest + MSW, Playwright.

**Spec:** `../specs/2026-10-20-s5-answer-chat-design.md` (decisions 1-12 are this plan's contract; section 3 is the API shape, section 5 the frontend design, section 7 the settings table).

**Worktree:** Execute in a dedicated worktree off `master` (repo rule: every task in a worktree so parallel work cannot interfere).

## Global Constraints

- Ruff line length 110; docstrings on every module/class/function, private ones too (`tests/test_style.py` enforces); blank line after every docstring; comments start capitalized, end with a period.
- All parameters keyword-only (`def f(*, a, b)`), including calls to third-party code; no `# type: ignore` unless unavoidable; precise annotations.
- Backend gates before every commit, run from `backend/` with the repo venv: `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest` (against the compose Postgres).
- Web gates before every web commit, run from `web/`: `npm run test`, `npm run lint`, `npm run format:check`.
- No Alembic migration this slice: `origin` rides the existing `query_logs.params` JSONB (spec decision 9). `app/retrieval` gains no LLM dependency; only the `origin` parameter changes there.
- `rerank` is accepted, logged, ignored until S6 (spec decision 5). Chat retrieval defaults are settings, not schema: `answer_context_chunks = 10` (1..50), `answer_max_chunks_per_document = 3` (>= 1); request `top_k`/`max_chunks_per_document` overrides beat them (spec decisions 3, 5).
- Exact copy pinned by this plan: stub answer `This is a stub answer grounded in the supplied context passages. [1]`; canned empty answer `No indexed content in this project matches your question yet.`; Groq failure copy `The answer could not be generated right now. Please try again.` (the 502 detail is exactly this string); 404 detail `project not found`.
- Settings: `llm_provider: Literal["stub", "groq"] = "stub"`, `groq_base_url = "https://api.groq.com/openai/v1"`, `groq_model = "openai/gpt-oss-20b"`, `llm_timeout_seconds = 30.0` (> 0), `llm_max_tokens = 1024` (> 0), `groq_api_key` required non-empty when `llm_provider == "groq"` (spec section 7).
- Non-streaming, single JSON `{answer, chunks}`; single-turn; no new frontend routes; the URL stays `/projects/:projectId` (spec decisions 1-3).
- httpx moves from the dev extra to the runtime `[project] dependencies` in `backend/pyproject.toml` (the Dockerfile installs runtime deps only; same `>=0.28` floor, no new package).
- Commit style: one concern per commit; never add agent co-author lines.

## Review Focus

Input classes the spec implies but no happy path exercises - each pinned by the named test in its owning task:

1. Groq transport failure modes (timeout, 429/5xx, non-JSON body, missing `choices`, empty content) must surface as one fixed user-safe `LLMError`, never a raw httpx exception or a 500 - the failure tests in Task 2.
2. An empty index must not reach the LLM (free-tier cost, determinism) - `test_empty_index_returns_canned_answer_without_llm_call` (Task 4).
3. An LLM failure must not lose the query log row: `retrieve()` commits before the remote call, so a 502 still leaves the query logged - `test_llm_failure_maps_to_502_and_still_logs` (Task 5).
4. The origin marker must distinguish chat queries from direct `/retrieve` calls (the S8 labeling data) - `test_retrieve_logs_origin_direct_by_default` (Task 3) and `test_answer_logs_origin_answer` (Task 4).
5. The uploads polling must keep running while the Ask tab is active (both panels stay mounted) - `test_uploads_polling_continues_while_ask_tab_active` (Task 7).

## Task DAG

```
T1 llm protocol+stub+factory ──> T2 groq client ──────────────────────┐
T3 retrieve origin param ──> T4 answers module ──> T5 router+wiring ──┼──> T8 e2e+docs+gates
T6 chat api+panel ──> T7 project page tabs ────────────────────────────┘
```

T1, T3, and T6 are mutually independent (disjoint files) and may run in parallel. T2 consumes T1. T4 consumes T1 and T3. T5 consumes T4. T7 consumes T6. T8 consumes T2, T5, and T7.

---

### Task 1: LLM provider protocol, stub, factory, provider setting

**Files:**
- Modify: `backend/app/providers/base.py`
- Create: `backend/app/providers/stub_llm.py`
- Modify: `backend/app/providers/__init__.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/providers/test_stub_llm.py`, `backend/tests/test_config.py`

**Interfaces:**
- Consumes: the existing provider pattern (`Parser`/`EmbeddingProvider` protocols, factory style).
- Produces (used by Tasks 2, 4, 5):

```python
# app/providers/base.py
class LLMError(Exception):
    """Raised when an LLM provider cannot generate; its message is shown to users."""

class LLMProvider(Protocol):
    """Interface every LLM provider implements."""

    def generate(self, *, system: str, user: str) -> str:
        """Generate one completion from a system prompt and a user prompt."""

        ...

# app/providers/stub_llm.py
STUB_ANSWER: Final = "This is a stub answer grounded in the supplied context passages. [1]"

class StubLLMProvider:
    """Deterministic offline LLM for local development and tests."""

    def generate(self, *, system: str, user: str) -> str: ...

# app/providers/__init__.py
def get_llm_provider(*, settings: Settings) -> LLMProvider: ...

# app/core/config.py (after embedding_provider)
llm_provider: Literal["stub"] = "stub"
```

- [ ] **Step 1: Write the failing tests**

`tests/providers/test_stub_llm.py`:

- `test_stub_llm_is_deterministic`: two `generate` calls with the same prompts return the identical string, equal to `STUB_ANSWER`, and containing `"[1]"`.
- `test_stub_llm_ignores_prompt_content`: different system/user inputs return the same output.

`tests/test_config.py` addition:

- `test_llm_provider_setting_defaults`: `SettingsForTests().llm_provider == "stub"`.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/providers/test_stub_llm.py tests/test_config.py -v`
Expected: FAIL (`app.providers.stub_llm` does not exist; the setting is unknown).

- [ ] **Step 3: Implement**

`base.py`: append `LLMError` (mirror the `ParseError` docstring contract) and `LLMProvider` exactly as in the Produces block. `stub_llm.py`: `STUB_ANSWER` constant plus `StubLLMProvider.generate` returning it. `__init__.py`: import both, extend `__all__`, add `get_llm_provider` with the exhaustive `match`/`assert_never` factory body copied from `get_parser`. `config.py`: add `llm_provider: Literal["stub"] = "stub"` after `embedding_provider`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/providers/ tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/providers/ app/core/config.py tests/providers/test_stub_llm.py tests/test_config.py
git commit -m "feat(providers): add the llm provider interface and stub"
```

---

### Task 2: Groq LLM client over httpx

**Files:**
- Create: `backend/app/providers/groq_llm.py`
- Modify: `backend/app/providers/__init__.py` (groq factory case)
- Modify: `backend/app/core/config.py` (Literal extension, groq/llm settings, key validator)
- Modify: `backend/pyproject.toml` (httpx to runtime dependencies)
- Test: `backend/tests/providers/test_groq_llm.py`, `backend/tests/test_config.py`

**Interfaces:**
- Consumes: `LLMProvider`, `LLMError` (Task 1), `Settings`.
- Produces (used by Tasks 4, 5):

```python
# app/providers/groq_llm.py
GROQ_ERROR_COPY: Final = "The answer could not be generated right now. Please try again."

class GroqLLMProvider:
    """Groq LLM client against the OpenAI-compatible chat/completions endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Store the endpoint config and build one shared httpx client."""

    def generate(self, *, system: str, user: str) -> str:
        """Post one chat completion and return its message text."""
```

`generate` POSTs `{"model", "messages": [{"role": "system"}, {"role": "user"}], "max_tokens"}` to `/chat/completions` on the shared `httpx.Client` (bearer key header, `timeout_seconds`, injected `transport` so tests run hermetic). Every failure mode - `httpx.TimeoutException`, `httpx.HTTPError` (covers `raise_for_status`), malformed JSON (`ValueError`), missing keys (`KeyError`/`TypeError`) - raises `LLMError(GROQ_ERROR_COPY)` with `from error` so the chained cause survives for the server log. A 200 whose `choices[0].message.content` is not a non-empty string raises the same `LLMError`.

- [ ] **Step 1: Write the failing tests**

`tests/providers/test_groq_llm.py` - every test builds the provider around `httpx.MockTransport` with a handler closure (no network):

- `test_generate_returns_message_content`: a 200 body `{"choices": [{"message": {"content": "Rotate the key. [1]"}}]}` returns `"Rotate the key. [1]"`.
- `test_generate_sends_model_key_and_messages`: the handler captures the request; assert the URL path is `/chat/completions`, the `Authorization` header is `Bearer gsk-test`, and the JSON body carries the model, `max_tokens: 1024`, and both messages in system-then-user order.
- `test_non_2xx_raises_user_safe_llm_error` (parametrized over 429 and 500): raises `LLMError` whose `str` matches `could not be generated right now`.
- `test_timeout_raises_llm_error`: the handler raises `httpx.ConnectTimeout`; `LLMError`, same copy.
- `test_malformed_body_raises_llm_error`: a 200 with body `not json`; `LLMError`.
- `test_missing_choices_raises_llm_error`: a 200 with body `{}`; `LLMError`.
- `test_empty_content_raises_llm_error` (parametrized over `""` and `"   "`); `LLMError`.

`tests/test_config.py` additions:

- `test_llm_settings_defaults`: `groq_base_url == "https://api.groq.com/openai/v1"`, `groq_model == "openai/gpt-oss-20b"`, `llm_timeout_seconds == 30.0`, `llm_max_tokens == 1024`.
- `test_groq_provider_requires_key`: `SettingsForTests(llm_provider="groq")` raises `ValidationError`; with `groq_api_key="k"` it constructs.
- `test_llm_settings_reject_nonpositive` (parametrized over `llm_timeout_seconds=0` and `llm_max_tokens=0`): `ValidationError`.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/providers/test_groq_llm.py tests/test_config.py -v`
Expected: FAIL (`app.providers.groq_llm` does not exist; settings unknown).

- [ ] **Step 3: Implement**

`groq_llm.py` per the Produces block. `config.py`: widen `llm_provider` to `Literal["stub", "groq"]`, add `groq_api_key: str = ""`, `groq_base_url`, `groq_model`, `llm_timeout_seconds: float = Field(default=30.0, gt=0)`, `llm_max_tokens: int = Field(default=1024, gt=0)`, and a `model_validator(mode="after")` `_require_groq_key` rejecting an empty key when `llm_provider == "groq"`. `__init__.py`: import `GroqLLMProvider`, add the `case "groq":` factory arm building it from settings. `pyproject.toml`: move `"httpx>=0.28"` from the `dev` extra into `[project] dependencies` (runtime import; the Dockerfile installs runtime deps only).

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/providers/ tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/providers/ app/core/config.py pyproject.toml tests/providers/test_groq_llm.py tests/test_config.py
git commit -m "feat(providers): add the groq llm client"
```

---

### Task 3: `retrieve()` origin parameter

**Files:**
- Modify: `backend/app/retrieval/service.py` (retrieve signature, `_log_query`)
- Test: `backend/tests/retrieval/test_service.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces (used by Task 4): `retrieve(*, db, project_id, user_id, params, settings, origin: str = "direct") -> list[RetrievedChunk]` - `origin` recorded at `params["origin"]` in the `query_logs` row.

- [ ] **Step 1: Write the failing tests** in `tests/retrieval/test_service.py`

- `test_retrieve_logs_origin_direct_by_default`: after a plain `retrieve(...)`, the log row's `params["origin"] == "direct"`.
- `test_retrieve_records_explicit_origin`: `retrieve(..., origin="answer")` writes `params["origin"] == "answer"`.

Both follow `test_retrieve_writes_one_query_log_row`'s seeding and row-fetch pattern.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/retrieval/test_service.py -v`
Expected: FAIL (`retrieve()` got an unexpected keyword argument `origin` / key absent).

- [ ] **Step 3: Implement**

Add the `origin: str = "direct"` keyword-only parameter to `retrieve`, thread it through `_log_query` (new `origin: str` parameter), and write `"origin": origin` into the `params` dict. No other behavior changes.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/retrieval/ -v`
Expected: PASS (the existing log test asserts individual keys, so the new key breaks nothing).

- [ ] **Step 5: Commit**

```bash
git add app/retrieval/service.py tests/retrieval/test_service.py
git commit -m "feat(retrieval): record the query origin in query_logs"
```

---

### Task 4: Answers module - schemas, prompt, service

**Files:**
- Create: `backend/app/answers/__init__.py`, `backend/app/answers/schemas.py`, `backend/app/answers/prompt.py`, `backend/app/answers/service.py`
- Modify: `backend/app/retrieval/schemas.py` (extract the shared `QueryText` type)
- Modify: `backend/app/core/config.py` (two answer settings)
- Modify: `backend/tests/fakes.py` (LLM fakes)
- Test: `backend/tests/answers/__init__.py`, `backend/tests/answers/test_prompt.py`, `backend/tests/answers/test_service.py`, `backend/tests/test_config.py`

**Interfaces:**
- Consumes: `get_llm_provider`, `LLMProvider` (Task 1); `retrieve` with `origin` (Task 3); `RetrievedChunk`, `RetrieveIn`, `RetrievedChunkOut`, `MAX_QUERY_CHARS` (`app.retrieval`).
- Produces (used by Task 5):

```python
# app/retrieval/schemas.py - extracted so both /retrieve and /answer share one query contract
def _reject_nul(value: str) -> str:  # noqa: PLR0917
    """Reject NUL bytes, which Postgres text parameters cannot carry."""

QueryText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUERY_CHARS),
    AfterValidator(_reject_nul),
]
# RetrieveIn.query and AnswerIn.query both become: query: QueryText

# app/answers/schemas.py
class AnswerIn(BaseModel):
    """One answer request body: the query plus optional retrieval overrides."""

    query: QueryText
    top_k: int | None = Field(default=None, ge=1, le=50)
    rerank: bool = False
    max_chunks_per_document: int | None = Field(default=None, ge=1)

class AnswerOut(BaseModel):
    """One generated answer with the exact chunks that grounded it."""

    answer: str
    chunks: list[RetrievedChunkOut]

# app/answers/prompt.py - pure, no SQLAlchemy
SYSTEM_PROMPT: Final = (
    "Answer the user's question using only the supplied context passages. "
    "Cite the passage numbers you used inline, like [1] or [2]. "
    "If the context does not contain the answer, say so plainly. Be concise."
)

def build_user_prompt(*, query: str, chunks: list[RetrievedChunk]) -> str:
    """Render the question and the numbered context blocks in rank order."""

# one block per chunk: "[{n}] {filename} - {heading path joined by ' > '}"
# (filename alone when heading_path is empty), then the chunk text; blocks
# joined by blank lines after a "Question: {query}" header line.

# app/answers/service.py
CANNED_EMPTY_ANSWER: Final = "No indexed content in this project matches your question yet."

@dataclass(frozen=True)
class Answer:
    """One generated answer plus the retrieval rows that grounded it."""

    text: str
    chunks: list[RetrievedChunk]

def generate_answer(
    *, db: Session, project_id: UUID, user_id: UUID, params: AnswerIn, settings: Settings
) -> Answer:
    """Resolve the retrieval defaults, retrieve, prompt, and generate one answer."""

# app/core/config.py (after rrf_k)
answer_context_chunks: int = Field(default=10, ge=1, le=50)
answer_max_chunks_per_document: int = Field(default=3, ge=1)

# tests/fakes.py
class RecordingLLMProvider:
    """LLM provider that records every call and returns a fixed answer."""
    # __init__(*, answer: str); generate appends (system, user) to self.calls

class RaisingLLMProvider:
    """LLM provider whose every generation raises; pins the 502 mapping."""
    # generate raises LLMError("The answer service is down for maintenance.")
```

`generate_answer` resolves a `RetrieveIn` (`top_k = params.top_k ?? settings.answer_context_chunks`, `max_chunks_per_document = params.max_chunks_per_document ?? settings.answer_max_chunks_per_document`, `rerank` echoed), calls `retrieve(..., origin="answer")`, returns the canned answer on an empty chunk list **without calling the LLM**, and otherwise calls `get_llm_provider(settings=settings).generate(system=SYSTEM_PROMPT, user=build_user_prompt(...))`. `app/answers/__init__.py` is a module docstring only. Update the `max_chunks_per_document` comment in `app/retrieval/schemas.py`: the S5 chat round now resolves it against `answer_max_chunks_per_document`; direct `/retrieve` stays unbounded by default.

- [ ] **Step 1: Write the failing settings tests** in `tests/test_config.py`

`test_answer_settings_defaults_and_bounds`: defaults `10`/`3`; `answer_context_chunks` rejects `0` and `51`; `answer_max_chunks_per_document` rejects `0` (follow the `test_retrieval_settings_reject_nonpositive` pattern).

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (unknown fields).

- [ ] **Step 3: Add the two settings** per the Produces block.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing prompt tests** in `tests/answers/test_prompt.py`

Build `RetrievedChunk` values directly (uuid4 ids, `heading_path` lists). Tests:

- `test_blocks_numbered_in_rank_order`: two chunks; `"[1]"` appears before `"[2]"`; both chunk texts present.
- `test_block_headers_render_filename_and_heading`: `heading_path=["Keys", "Rotation"]`, `filename="handbook.pdf"` -> a block header line `[1] handbook.pdf - Keys > Rotation`.
- `test_empty_heading_path_renders_filename_only`: `heading_path=[]` -> header `[1] handbook.pdf` with no `- ` suffix.
- `test_question_included`: the prompt contains `Question: how do I rotate the garage key`.
- `test_system_prompt_instructs_citations`: `SYSTEM_PROMPT` contains `"[1]"` and the words `only` and `concise`.

- [ ] **Step 6: Run to verify failure**

Run: `pytest tests/answers/test_prompt.py -v`
Expected: FAIL (`app.answers.prompt` does not exist).

- [ ] **Step 7: Implement the module and the schema refactor**

`app/answers/prompt.py` per the Produces block. In `app/retrieval/schemas.py`: move the NUL check into the module-level `_reject_nul` (`# noqa: PLR0917` - pydantic validators receive the value positionally), define `QueryText`, and change `RetrieveIn.query` to `query: QueryText` (delete the class-level `field_validator`). Create `app/answers/schemas.py` per the Produces block and `app/answers/__init__.py`.

- [ ] **Step 8: Run to verify the refactor kept the contract**

Run: `pytest tests/answers/test_prompt.py tests/retrieval/ -v`
Expected: PASS - the existing retrieval API tests (NUL, strip, 2001-char) prove the `QueryText` extraction changed no behavior.

- [ ] **Step 9: Write the failing service tests** in `tests/answers/test_service.py`

Seeding: `seed_project` + `seed_document_with_chunks`; `SettingsForTests()` for defaults, `monkeypatch.setenv("RAG_ANSWER_CONTEXT_CHUNKS", ...)` for per-test overrides. Tests:

- `test_answer_chunks_equal_retrieval_final_chunks`: seeded `["alpha alpha"]`; `generate_answer(query="alpha")` returns `text == STUB_ANSWER` and chunk ids equal `retrieve(..., origin="answer")`'s.
- `test_empty_index_returns_canned_answer_without_llm_call`: no chunks seeded; monkeypatch `app.answers.service.get_llm_provider` to return a `RecordingLLMProvider`; result is `CANNED_EMPTY_ANSWER` with `chunks == []` and `provider.calls == []`.
- `test_answer_logs_origin_answer`: after `generate_answer`, the project's `QueryLog.params["origin"] == "answer"`.
- `test_request_overrides_beat_settings`: 12 seeded chunks in one document; `AnswerIn(query="alpha", top_k=2)` returns 2 chunks.
- `test_settings_defaults_apply_when_request_omits`: 12 chunks spread across four documents (3 each) so no cap binds; no overrides -> 10 chunks (the `answer_context_chunks` default, not `RetrieveIn`'s). Then one document holding 5 chunks that all match the query, no overrides -> 3 returned (the `answer_max_chunks_per_document` default capping a document that `top_k=10` alone would not).

- [ ] **Step 10: Run to verify failure**

Run: `pytest tests/answers/test_service.py -v`
Expected: FAIL (`app.answers.service` does not exist).

- [ ] **Step 11: Implement `app/answers/service.py`** per the Produces block; add `RecordingLLMProvider` and `RaisingLLMProvider` to `tests/fakes.py`.

- [ ] **Step 12: Run to verify pass**

Run: `pytest tests/answers/ tests/retrieval/ tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 13: Commit**

```bash
git add app/answers/ app/retrieval/schemas.py app/core/config.py tests/answers/ tests/fakes.py tests/test_config.py
git commit -m "feat(answers): add the answer schemas, prompt, and service"
```

---

### Task 5: Answers router and API wiring

**Files:**
- Create: `backend/app/answers/router.py`
- Modify: `backend/app/main.py` (include the router)
- Test: `backend/tests/answers/test_answer_api.py`

**Interfaces:**
- Consumes: `generate_answer`, `Answer` (Task 4); `get_current_user`, `get_project_visible_to_user`, `get_db`, `get_settings`; the conftest `client` fixture.
- Produces: `POST /api/projects/{project_id}/answer` returning `AnswerOut` (registered via `app.include_router(answers_router, prefix="/api")` after `retrieval_router`).

- [ ] **Step 1: Write the failing tests** in `tests/answers/test_answer_api.py`

House pattern: copy `_create_project` from `tests/retrieval/test_retrieve_api.py`; seed with `seed_document_with_chunks`; monkeypatch `app.answers.service.get_llm_provider` for the 502 test (returning `RaisingLLMProvider()`). Tests:

- `test_answer_requires_auth`: no token -> `401`.
- `test_answer_404_for_invisible_project`: another user's private project -> `404`, detail `project not found`.
- `test_answer_works_for_public_project_non_member`: owner patches `is_public`, non-member asks -> `200` with `answer == STUB_ANSWER` and a non-empty `chunks`.
- `test_answer_validation_errors` (parametrized): `{"query": "   "}`, `{"query": "x" * 2001}`, `{"query": "\u0000x"}`, `{"query": "x", "top_k": 0}`, `{"query": "x", "top_k": 51}`, `{"query": "x", "max_chunks_per_document": 0}` -> `422`.
- `test_answer_strips_and_matches`: seeded `"alpha alpha"`; `{"query": "  alpha  "}` -> `200`, first chunk's `text == "alpha alpha"`, `answer == STUB_ANSWER`.
- `test_rerank_true_accepted_and_ignored`: `rerank: true` and `rerank: false` return identical bodies.
- `test_answer_empty_project_returns_canned`: no chunks -> `200`, `answer == CANNED_EMPTY_ANSWER`, `chunks == []`, exactly one `QueryLog` row.
- `test_answer_response_shape`: response keys exactly `{"answer", "chunks"}`; chunk items carry exactly the nine `RetrievedChunkOut` fields.
- `test_llm_failure_maps_to_502_and_still_logs`: seeded chunks plus the raising provider -> `502` with detail `The answer service is down for maintenance.`, and the project's `QueryLog` row exists with `params["origin"] == "answer"` (the log committed before the remote call).
- `test_error_paths_log_nothing`: the 401, 404, and 422 paths write no `QueryLog` rows.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/answers/test_answer_api.py -v`
Expected: FAIL (route does not exist - 404 on POST).

- [ ] **Step 3: Implement the router and wire it**

`router.py` in the house style (`sources/router.py`, `retrieval/router.py`): a module logger; a private `_to_out(*, chunk: RetrievedChunk) -> RetrievedChunkOut` field-for-field mapper; the endpoint `answer_question(*, project_id: UUID, body: AnswerIn, user, db, settings) -> AnswerOut` that resolves the project (`None` -> `HTTPException(404, "project not found")`), wraps `generate_answer` in `try/except LLMError` logging `logger.warning("Answer generation failed", exc_info=error)` before `raise HTTPException(502, str(error)) from error`, and maps the `Answer` into `AnswerOut`. `app/main.py`: import and include the router after `retrieval_router`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/answers/ tests/test_api_prefix.py tests/test_cors.py -v`
Expected: PASS - the prefix test sees the new route under `/api`.

- [ ] **Step 5: Commit**

```bash
git add app/answers/router.py app/main.py tests/answers/test_answer_api.py
git commit -m "feat(api): expose POST /projects/{id}/answer"
```

---

### Task 6: Chat API and panel

**Files:**
- Create: `web/src/features/chat/answersApi.ts`
- Create: `web/src/features/chat/ChatPanel.tsx`
- Modify: `web/src/test/setup.ts` (jsdom `scrollIntoView` stub)
- Test: `web/src/features/chat/ChatPanel.test.tsx`

**Interfaces:**
- Consumes: the shared `api` instance and `getErrorMessage` (`web/src/app/api.ts`).
- Produces (used by Task 7):

```typescript
// answersApi.ts
export type RetrievedChunk = {
  id: string; document_id: string; source_item_id: string; filename: string;
  position: number; heading_path: string[]; chunk_type: string; text: string; score: number;
};
export type Answer = { answer: string; chunks: RetrievedChunk[] };
export const answersApi = api.injectEndpoints({
  endpoints: (build) => ({
    askQuestion: build.mutation<Answer, { projectId: string; body: { query: string } }>({
      query: ({ projectId, body }) => ({ url: `/projects/${projectId}/answer`, method: "POST", body }),
    }),
  }),
});
export const { useAskQuestionMutation } = answersApi;

// ChatPanel.tsx
export default function ChatPanel({ projectId }: { projectId: string }): JSX.Element
```

`ChatPanel` behavior contract (spec section 5): local state only - `turns: Turn[]` where `Turn = { id: number; question: string; answer?: string; chunks?: RetrievedChunk[]; error?: string }` - plus the controlled input text. Submitting appends a turn and awaits `askQuestion(...).unwrap()`; success fills `answer`/`chunks`, failure fills `error` via `getErrorMessage`. The newest turn renders a "Thinking..." placeholder while the mutation is pending. The input is a multiline MUI `TextField` (`label="Ask a question"`, house `TextField` pattern from `LoginPage.tsx`): Enter submits, Shift+Enter inserts a newline, and both the field and the "Ask" `Button` are disabled while pending or when the input is empty. Each answered turn renders the answer as plain text preserving newlines (`whiteSpace: "pre-wrap"`, `[n]` markers as-is), then a collapsed `Sources (n)` MUI Accordion whose rows are one inner Accordion per chunk - summary `[i] filename > heading path joined by " > "` (filename alone when the path is empty), details the chunk text. An errored turn renders an `Alert` plus a "Try again" `Button` that re-sends that turn's question into the same turn. A bottom sentinel ref auto-scrolls on `turns`/pending changes (hence the setup stub: jsdom implements neither `scrollIntoView`).

- [ ] **Step 1: Write the failing tests** in `web/src/features/chat/ChatPanel.test.tsx`

Render with `renderWithProviders(<ChatPanel projectId="p-1" />, { preloadedState: authed() })`; MSW handler `http.post("*/api/projects/p-1/answer", ...)`; fixture `answerFixture = { answer: "Rotate the garage key from the admin UI. [1]", chunks: [{ id: "c-1", document_id: "d-1", source_item_id: "s-1", filename: "handbook.pdf", position: 0, heading_path: ["Keys", "Rotation"], chunk_type: "text", text: "To rotate the key, open the admin UI and click Rotate.", score: 0.75 }] }`. Tests:

- `asks a question and renders the answer`: fill `Ask a question`, click the Ask button; `findByText(/Rotate the garage key/)` appears; the question text also renders.
- `enter submits and shift-enter inserts a newline`: type `first line`, `{Shift>}{Enter}{/Shift}` (no post yet, the field holds a newline), then `{Enter}` -> exactly one post with `query === "first line\n"`.
- `keeps the input disabled while the request is pending`: a deferred handler; after submit, the Ask button and the textbox are both disabled (jest-dom `toBeDisabled()` - both are native elements carrying the native `disabled` attribute); resolving re-enables them.
- `lists and expands the answer sources`: after the answer, `Sources (1)` is visible; clicking it reveals the row `[1] handbook.pdf > Keys > Rotation`; expanding the row reveals the chunk text.
- `shows an error card and try again re-sends`: first response `500 {detail: "boom"}`, retry `200 answerFixture`; the alert shows the server copy; clicking Try again posts again (2 posts total) and renders the answer.

- [ ] **Step 2: Run to verify failure**

Run: `npm run test -- ChatPanel`
Expected: FAIL (module does not exist).

- [ ] **Step 3: Implement**

`answersApi.ts` exactly as in the Produces block (no tag types - nothing cacheable). `ChatPanel.tsx` per the behavior contract. `setup.ts`: add `window.HTMLElement.prototype.scrollIntoView = () => {};` with a comment (jsdom does not implement it; the thread's auto-scroll effect needs the no-op).

- [ ] **Step 4: Run to verify pass**

Run: `npm run test -- ChatPanel` then `npm run lint` then `npm run format:check`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/features/chat/ src/test/setup.ts
git commit -m "feat(web): add the chat panel"
```

---

### Task 7: Project page tabs

**Files:**
- Modify: `web/src/features/projects/ProjectPage.tsx`
- Test: `web/src/features/projects/ProjectPage.test.tsx` (update existing, add new)

**Interfaces:**
- Consumes: `ChatPanel` (Task 6), `useProjectUploads`, the existing `UploadCard`/`UploadsTable`.
- Produces: the two-tab page. No exports change.

**Tab rule (spec decision 3):** `pinnedTab: "ask" | "documents" | null` starts `null`; `activeTab = pinnedTab ?? (hasReadyUpload ? "ask" : "documents")` where `hasReadyUpload = (uploads ?? []).some((u) => u.status === "ready")`. The Ask `Tab` is `disabled={!hasReadyUpload}`; any manual tab click sets `pinnedTab`. Both panels render permanently, each wrapped in a `Box` with `hidden={activeTab !== "..."}` so the chat thread survives tab switches and the uploads polling never stops. The MUI `Tabs` bar sits under the page header; the URL is unchanged.

- [ ] **Step 1: Update the tests**

The baseline MSW uploads include a `ready` row, so Ask is the default tab and role/label queries stop seeing the hidden Documents panel. Existing tests that assert Documents content must first click the tab: `renders the header, back link, upload card, and status chips`; `uploads the chosen file as multipart form data`; `keeps Upload disabled while the request is pending`; `rejects a file with an unsupported extension`; `rejects a file over the 25MB limit`; `rejects an empty file`; `keeps the upload control a single tab stop`; `shows friendly copy when the server rejects the upload with 422`; `shows friendly copy when storage is unavailable (503)`; `shows the server's 409 copy`. Add `await user.click(screen.getByRole("tab", { name: "Documents" }))` (or the `userEvent.setup()` equivalent already in scope) as the first interaction of each. `keeps the upload control a single tab stop` also needs its sequence updated: the Tabs bar now sits between the back link and the upload input, and the selected tab is focusable (MUI roving tabindex), so tabbing from the back link visits the selected Documents tab before the upload input - keep the core assertion that the label Button is not a stop. The polling, error-state, and not-found tests need no change.

New tests:

- `ask tab is the default when a ready upload exists`: baseline handlers; the Ask tab has `aria-selected="true"`, `queryByRole("cell", { name: "brief.pdf" })` is `null` (hidden from the a11y tree), and the chat input `getByLabelText("Ask a question")` is visible.
- `ask tab is disabled and documents active without a ready upload`: override the uploads handler to return only `queuedUpload` and `failedUpload`; the Ask tab is disabled (`toBeDisabled()` - MUI renders a Tab as a native button carrying the native `disabled` attribute), Documents has `aria-selected="true"`, and `brief.pdf`'s cell is visible.
- `clicking a tab pins the choice`: with the baseline (ready exists), click Documents; Documents stays selected with visible cells even though `hasReadyUpload` is true.
- `the thread survives a tab round trip`: with an `/api/projects/p-1/answer` handler returning the fixture; on Ask, ask a question, await the answer, click Documents, click Ask; the answer text is still visible.
- `uploads polling continues while the ask tab is active` (Review Focus 5): fake timers; override uploads to `[readyUpload, queuedUpload]` (Ask active by default, one row still moving); `advance(0)` -> 1 fetch, `advance(2000)` -> 2 fetches.

- [ ] **Step 2: Run to verify failure**

Run: `npm run test -- ProjectPage`
Expected: FAIL (no tabs render).

- [ ] **Step 3: Implement the restructure**

Add the `ProjectTab` type, `pinnedTab` state, `hasReadyUpload`, and `activeTab` per the tab rule. Render the `Tabs` bar (`<Tab label="Ask" value="ask" disabled={!hasReadyUpload} />`, `<Tab label="Documents" value="documents" />`) after the header `Stack`, then the two hidden-gated `Box` panels: Ask wraps `{projectId !== undefined && <ChatPanel projectId={projectId} />}`; Documents wraps the existing `UploadCard` and table/skeleton/error block unchanged.

- [ ] **Step 4: Run to verify pass**

Run: `npm run test` then `npm run lint` then `npm run format:check`
Expected: the whole web unit suite passes.

- [ ] **Step 5: Commit**

```bash
git add src/features/projects/ProjectPage.tsx src/features/projects/ProjectPage.test.tsx
git commit -m "feat(web): add ask and documents tabs to the project page"
```

---

### Task 8: E2E journey, docs, and full-branch gates

**Files:**
- Modify: `web/e2e/journey.spec.ts`
- Modify: `README.md`
- Modify: `docs/2026-10-19-system-overview.md`
- Modify: `docs/superpowers/specs/2026-10-06-roadmap.md`
- Modify: `docs/superpowers/specs/2026-10-20-s5-answer-chat-design.md` (status flip)
- Modify (as needed): `docs/backlog.md`

**Interfaces:**
- Consumes: every earlier task (the full stack: compose infrastructure, the e2e webServer config's stub-LLM API).
- Produces: the extended browser journey, the updated docs, a green branch.

- [ ] **Step 1: Extend the journey**

In `register -> default project -> upload pdf and docx -> ready`: immediately after the `tiny.pdf` row assertion, click the Documents tab (pins the choice - the tab would otherwise auto-flip to Ask the moment the first upload turns ready, hiding the cells the Ready assertions wait on; comment this). After the existing 409 re-upload block, append the ask flow: click the Ask tab; fill `Ask a question` with `What is this document about?`; click the Ask button; `await expect(page.getByText(/This is a stub answer grounded/i)).toBeVisible()`; click the `Sources (n)` summary (`getByRole("button", { name: /Sources \(\d+\)/ })` - MUI renders AccordionSummary as a native button); then assert the source rows with `getByRole("button", { name: /tiny\.pdf/ })` and `getByRole("button", { name: /sample\.docx/ })` visible (both files' chunks surface: an unrelated query ties every chunk at cosine distance 1, the vector leg returns them all, and the caps do not bind; the row-button selector avoids a strict-mode double match with the hidden Documents panel's table cells).

- [ ] **Step 2: Run the journey**

Run (compose Postgres/RabbitMQ/Garage up): `npm run e2e -- journey`
Expected: PASS - the full question -> grounded answer -> browser path, offline.

- [ ] **Step 3: Commit**

```bash
git add e2e/journey.spec.ts
git commit -m "test(e2e): ask through the browser journey"
```

- [ ] **Step 4: Update the docs**

`README.md`: reword the intro's last sentence (answers/chat are done, not landing); add `/answer` to the endpoints paragraph; add a short "Opting in to Groq" note in the run section - the default stack stays offline on `llm_provider=stub`; setting `RAG_LLM_PROVIDER=groq` and `RAG_GROQ_API_KEY` on the `api` service (compose `environment:` or an override file) routes answers through `openai/gpt-oss-20b`; failures answer 502. `docs/2026-10-19-system-overview.md`: refresh the snapshot date; add the Answers route row (`POST /api/projects/{project_id}/answer` - ProjectPage Ask tab / ChatPanel); replace the "There is no external AI service yet" note with the LLM provider layer sentence (stub default, Groq opt-in); note `query_logs.params.origin` (`direct` vs `answer`). `docs/superpowers/specs/2026-10-06-roadmap.md`: status line and closing paragraph record S5 as implemented under this plan, next slice S6. `docs/superpowers/specs/2026-10-20-s5-answer-chat-design.md`: status flips to implemented/frozen (the S4 spec's header is the precedent).

- [ ] **Step 5: Commit the docs**

```bash
git add README.md docs/
git commit -m "docs: record the s5 slice as implemented"
```

- [ ] **Step 6: Run the full-branch gates**

From `backend/`: `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest`. From `web/`: `npm run test`, `npm run lint`, `npm run format:check`, `npm run build` (the `tsc -b` type gate). Expected: all green. Any failure is a defect in an earlier task - fix it in the owning task's files with its own commit, then rerun.

- [ ] **Step 7: Backlog residuals**

Append any deferrals this branch's reviews raised to `docs/backlog.md` under a timestamped `## 2026-10-20 - S5 answer and chat` header, each line linking its commit. The known carried items stay put. If nothing new was raised, skip - do not create an empty section; if the only edit is this file, commit it as `docs(backlog): record the s5 residuals`.
