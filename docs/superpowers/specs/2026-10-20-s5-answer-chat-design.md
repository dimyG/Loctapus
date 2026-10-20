# S5 - `/answer` + chat UI (free-tier LLM) - Design

Date: 2026-10-20
Status: Approved design (2026-10-20 round); implemented on the `s5-answer-chat` branch
(`../plans/2026-10-20-s5-answer-chat.md`, merge pending). Frozen: decisions below are as built.
Source of truth: `../../2026-10-06-initial_rag_mvp_agent_project_context.md` (the "MD") and
`2026-10-06-roadmap.md` (the "slices spec"). Where those disagree with this document on S5
topics, this document wins; where this document is silent, they govern.

## 1. Context

S5 is the chat + answer-generation slice (slices spec section 2, decision 7): `POST
/api/projects/{project_id}/answer` calls the S4 retrieval internally, builds a grounded
prompt from the final chunks, and returns the answer with its cited chunks. The LLM runs on
Groq's free tier (`openai/gpt-oss-20b`, MD section 16) - the first server-side provider key -
behind an `LLMProvider` interface whose stub implementation keeps the test suite offline
(decision-2 provider pattern). Frontend pairing resumes here (decision 5; S4 was the
backend-only exception): the chat view is the retrieval-facing UI.

Done-when (slices spec section 2): question -> answer grounded in cited chunks, from the
browser.

S4 left this slice two hooks: the product default for `max_chunks_per_document` is "the S5
chat round's call" (S4 decision 10), and the ranked grounded chunks surface as the answer's
citations. The backlog's nginx `proxy_read_timeout` watch item is resolved by this slice's
own timeout (decision 12).

## 2. Decisions (2026-10-20 design round, user-approved)

1. **Non-streaming.** One JSON response `{answer, chunks}`; the provider interface is a
   single request -> string call. SSE/token streaming was rejected for MVP scope (streaming
   provider interface, SSE through nginx, incremental rendering, different test strategy);
   it can be added later behind a new interface variant without redesigning this one.
2. **Single-turn.** Every question is grounded only in retrieval; there is no conversation
   memory. The UI renders a scrollable thread of past question/answer pairs, but each
   question must be self-contained. The thread is client-side display history, lost on
   reload. No conversation tables, no context management - matching the MD's "no query
   rewriting/decomposition/agentic loops" MVP line and keeping `/answer` a pure function.
3. **Layout: tabs, "Ask" default, empty-project rule.** The project page becomes a two-tab
   MUI page: Ask (the chat) and Documents (today's upload card + table). Ask is the default
   once the project has content; on an empty project the Ask tab is disabled and Documents
   is active. The active tab follows the data until the user picks one: Documents while the
   uploads list is loading or no upload is `ready`; Ask once a first `ready` upload exists;
   any manual tab click pins the user's choice. Both panels stay mounted (hidden, not
   unmounted) so the chat thread survives tab switches and the uploads polling continues on
   Ask. No new routes: the URL stays `/projects/:projectId`.
4. **Inline `[n]` citation markers.** The prompt numbers the context blocks `[1]..[n]` and
   instructs the model to cite the blocks it used inline. The response's `chunks` array is
   the exact final retrieval output in `[n]` order, so the UI's numbered sources list maps
   1:1 onto the markers. Imperfect model compliance (sparse or missing markers) is
   tolerated: the sources list still grounds the answer. The stub LLM emits a deterministic
   `[1]` citation so tests stay stable.
5. **Chat retrieval defaults live in settings, not the schema.** `answer_context_chunks = 10`
   (the answer path's top_k) and `answer_max_chunks_per_document = 3` (the S4-deferred
   product default, user-picked). The request may override `top_k`, `rerank`, and
   `max_chunks_per_document` - the same fields `/retrieve` accepts, so the S6 chat controls
   plug straight in - but the chat UI sends only the query. This matches S4's split: API
   contract limits are schema constants, tuning quantities are settings (MD section 13).
6. **A separate `app/answers/` module on top of retrieval.** Answer generation is its own
   layer (MD section 1: "Answer generation is a separate layer built on top of retrieval"),
   so it gets its own package and depends on `app/retrieval`, never the reverse. The answer
   service calls `retrieve()` as a Python function - no HTTP loopback, no self-auth, one
   session - and `app/retrieval/` keeps its clean future-service-split boundary: it gains
   no LLM dependency at all.
7. **LLM provider behind the existing providers pattern.** `LLMProvider` Protocol (sync
   `generate`, like `Parser`/`EmbeddingProvider`), `LLMError` with a user-safe message
   (the `ParseError` contract), a deterministic stub, a Groq implementation over **httpx**
   (~40 lines against the OpenAI-compatible `/chat/completions` endpoint), and
   `get_llm_provider` behind `llm_provider: Literal["stub", "groq"]` - the exhaustive-match
   factory the other providers use. httpx over the OpenAI SDK: zero new dependencies,
   explicit timeout and error control; no automatic retries (fast, honest failures instead -
   an interactive "Ask" click should fail visibly, not hang through hidden backoff).
8. **Empty-index short-circuit.** When retrieval returns no chunks, the endpoint answers
   with a canned "nothing relevant is indexed" message and an empty chunk list, and makes
   **no LLM call** - cheap, deterministic, honest. The query is still logged by `retrieve()`.
9. **`query_logs` origin marker.** `retrieve()` gains an `origin: str = "direct"` parameter
   (S5 passes `"answer"`), recorded in `params.origin`. No migration - `params` is JSONB.
   Rationale: chat queries are the real-user queries the S8 labeling workflow most wants;
   without the marker they are indistinguishable from direct API calls.
10. **Error mapping.** Any LLM provider failure surfaces as `502` carrying `LLMError`'s
    user-safe message; the specific cause is logged server-side. `401`/`404`/`422` are
    identical to `/retrieve`. The LLM call happens after `retrieve()` has committed its log
    row - no database transaction stays open across the remote call (MD section 30).
11. **Prompt shape (wording finalized at implementation).** System: answer only from the
    supplied context passages, cite the bracketed passage numbers inline, say plainly when
    the context does not contain the answer, be concise. User: the question, then one
    numbered block per chunk - a `[{n}] {filename} - {heading path}` header over the chunk
    text, chunks in retrieval order.
12. **Settings-bounded LLM call.** `llm_timeout_seconds = 30` fires well inside nginx's 60s
    `proxy_read_timeout` default, closing the backlog watch item for this endpoint; no
    compose/nginx change is needed. `llm_max_tokens = 1024` is the free-tier cost guard.

## 3. API contract

```
POST /api/projects/{project_id}/answer
Authorization: Bearer <jwt>

{
  "query": "how do I rotate the garage key",   // stripped, non-empty, <= 2000 chars,
                                               // no NUL bytes - the /retrieve rules
  "top_k": null,                    // optional override; null -> answer_context_chunks (10)
  "rerank": false,                  // accepted, logged, ignored until S6
  "max_chunks_per_document": null  // optional override; null ->
                                    //   answer_max_chunks_per_document (3)
}

200 ->
{
  "answer": "Generate a new key in the admin UI [1], then update both readers [2] and restart them [2].",
  "chunks": [ ...the RetrievedChunkOut shape from /retrieve, in [n] order... ]
}
```

- `chunks` are the exact final chunks that grounded the answer - the same objects
  `POST /projects/{id}/retrieve` returns for the same query - so the UI source numbering
  matches the inline markers.
- Empty index: `200` with the canned answer (decision 8) and `"chunks": []`.
- `401` without a valid token; `404 "project not found"` when neither team-visible nor
  public (`get_project_visible_to_user`, matching `/retrieve`); `422` for the same query
  bounds as `/retrieve` plus `top_k` (1..50) and `max_chunks_per_document` (>= 1) when
  overridden; `502 "could not generate an answer right now"` on LLM failure.
- `AnswerIn` reuses `MAX_QUERY_CHARS` and the NUL validator source from
  `app/retrieval/schemas.py`; `AnswerOut` embeds `list[RetrievedChunkOut]` from the same
  module - one source of truth for the chunk shape and its bounds.
- Validation constants live in the schemas (contract limits), while the two product
  defaults resolve in the service against settings (decision 5). `answer_context_chunks`
  is additionally capped at 50 in settings so the resolved `RetrieveIn` always validates.

## 4. Flow

```
POST /api/projects/{project_id}/answer (JWT)
  -> get_project_visible_to_user (404 semantics identical to /retrieve)
  -> resolve effective params (request override ?? setting default)
  -> retrieve(..., origin="answer")        # the S4 service, in-process:
                                           # embed -> legs -> RRF -> diversity walk
                                           # -> enrich -> query_logs row (committed)
  -> no chunks? -> 200 canned answer + []  # no LLM call (decision 8)
  -> build numbered context blocks         # pure function, rank order = [1]..[n]
  -> LLMProvider.generate(system, user)    # stub or Groq
  -> 200 { answer, chunks }
```

The Groq provider POSTs `{model, messages: [{role: "system"}, {role: "user"}], max_tokens}`
to `{groq_base_url}/chat/completions` with the bearer key, bounded by
`llm_timeout_seconds`; httpx timeouts, non-2xx statuses, and unparseable/empty bodies all
raise `LLMError` with user-safe copy. The stub returns a fixed sentence citing `[1]`.

## 5. Frontend design

```
web/src/features/chat/
  answersApi.ts   # RTK Query mutation: askQuestion({projectId, body}) -> Answer
  ChatPanel.tsx   # thread + input + sources
```

- **ProjectPage restructure**: `ProjectPage.tsx` owns the tab state (decision 3) and
  renders `<ChatPanel>` (Ask) and the existing `UploadCard` + `UploadsTable` (Documents).
  The `useProjectUploads` hook stays at the page level - the Ask-enabled rule reads its
  cached rows, and polling continues regardless of the active tab.
- **Thread**: `ChatPanel` local state - a list of turns `{question, answer?, chunks?,
  error?}`, newest at the bottom, auto-scrolled. Not Redux, not persisted: single-turn means
  the thread is display history only (decision 2).
- **Input**: MUI `TextField` + "Ask" button; Enter submits, Shift+Enter inserts a newline;
  disabled while a request is in flight or the input is empty. Over-long questions surface
  the backend's 422 copy through the shared `getErrorMessage`.
- **In flight**: a placeholder assistant bubble ("Thinking...") while the mutation is
  pending; the full answer replaces it on completion (non-streaming, decision 1).
- **Answer rendering**: plain text - no markdown renderer this slice; `[n]` markers render
  as-is. Under each answer, a collapsed "Sources (n)" MUI Accordion listing the chunks in
  order (`[1] handbook.pdf > Keys > Rotation`), each row expandable to the chunk text.
- **Errors**: a turn-level error card with the server's user-safe copy and a "Try again"
  button that re-sends the same question. A 401 flows through the shared session-expiry
  base query.
- **RTK Query**: a mutation (nothing cacheable, the component owns the thread), no new
  tag types; `Answer = { answer: string; chunks: RetrievedChunkOut[] }` mirrors the API.

## 6. Module layout

```
backend/
  app/
    answers/
      __init__.py
      schemas.py     # AnswerIn (query + optional overrides), AnswerOut
      prompt.py      # context blocks + prompt rendering: pure, no SQLAlchemy
      service.py     # resolve params -> retrieve() -> prompt -> LLM -> AnswerOut
      router.py      # POST /projects/{project_id}/answer, 502 mapping
    providers/
      base.py        # + LLMProvider protocol, LLMError
      stub_llm.py    # deterministic, offline
      groq_llm.py    # httpx chat/completions client
      __init__.py    # + get_llm_provider
    retrieval/
      service.py     # + origin parameter -> params.origin in query_logs
    main.py          # + answers router include
  alembic/versions/  # unchanged: no schema work in this slice
tests/
  providers/test_groq_llm.py
  providers/test_stub_llm.py
  answers/test_prompt.py
  answers/test_service.py
  answers/test_answer_api.py
web/src/features/chat/          # per section 5
web/src/features/projects/ProjectPage.tsx   # tabs + panel mounting
```

`app/answers` imports from `app/retrieval` (schemas, service) and `app.providers` - the
allowed directions; nothing from `retrieval` imports from `answers`.

## 7. Settings, compose, runbook

| Setting | Default | Validation |
|---|---|---|
| `llm_provider` | `"stub"` | `Literal["stub", "groq"]` |
| `groq_api_key` | `""` | non-empty required when `llm_provider == "groq"` (fail fast at boot, the existing validator pattern) |
| `groq_base_url` | `https://api.groq.com/openai/v1` | - |
| `groq_model` | `"openai/gpt-oss-20b"` | - |
| `llm_timeout_seconds` | `30` | > 0 |
| `llm_max_tokens` | `1024` | > 0 |
| `answer_context_chunks` | `10` | 1..50 (mirrors the API's top_k bound) |
| `answer_max_chunks_per_document` | `3` | >= 1 |

- **No compose change for the default stack**: `llm_provider=stub` keeps everything
  offline; the compose e2e journey stays keyless.
- **Opting in to Groq** (runbook step): set `RAG_LLM_PROVIDER=groq` and `RAG_GROQ_API_KEY`
  on the `api` service (compose `environment:` or an override file) - the first
  server-side provider key.
- `docs/2026-10-19-system-overview.md` gets its post-slice update (routes, flow, provider
  note) per AGENTS.md.

## 8. Testing approach

- **Groq provider, hermetic** (`tests/providers/test_groq_llm.py`): `httpx.MockTransport` -
  200 returns the text; 429/5xx/timeout raise `LLMError` with user-safe copy; the request
  carries model, bearer key, and both messages.
- **Stub provider** (`tests/providers/test_stub_llm.py`): deterministic output, cites
  `[1]`.
- **Prompt, pure** (`tests/answers/test_prompt.py`): blocks numbered in rank order,
  `filename - heading` headers, citation instructions present, question included.
- **Service, real Postgres, seeded chunks, stub LLM** (`tests/answers/test_service.py`):
  response chunks equal retrieval's final chunks; empty index returns the canned answer and
  makes no LLM call (spy on `generate`); `query_logs.params.origin == "answer"`; request
  overrides beat setting defaults; settings defaults apply when the request omits them.
- **API** (`tests/answers/test_answer_api.py`): 401; 404 for an invisible project; public
  project answerable by a non-member; 422 for the query bounds; 200 shape; a raising fake
  provider -> 502; `rerank: true` accepted and ignored.
- **Settings**: `llm_provider=groq` without a key is a construction error.
- **Frontend** (`ChatPanel.test.tsx`, updated `ProjectPage.test.tsx`; vitest + MSW):
  question -> answer renders; the sources accordion lists `[n] filename > heading` and
  expands to chunk text; input disabled while pending; 500 -> error card and Try again
  re-sends; Ask disabled + Documents active when no `ready` upload; Ask active when one
  exists; the thread survives a tab round trip.
- **Playwright e2e**: the existing journey extends past upload-`ready` - open Ask, ask a
  question, assert the stub answer and its sources render. The full question -> grounded
  answer -> browser path, offline, matching the slice's done-when.
- Full `ruff check`, `ruff format --check`, `mypy app tests`, `pytest` gate (AGENTS.md), plus
  the web `vitest`/`eslint` gate.

## 9. Out of scope (recorded, not built)

- Streaming (rejected this round) and multi-turn memory or persisted conversations
  (single-turn decision) - a later round can add either behind new interfaces.
- Markdown rendering of answers; clickable inline `[n]` anchors (plain text + numbered
  source list this slice).
- S6: `rerank` activation, retrieval controls in the chat UI, API keys.
- Answer-side persistence beyond the `query_logs` origin marker - no answer tables, no
  token-usage accounting (Groq's usage payload is ignored this slice).
- Retry/backoff around the LLM call - failures surface immediately as honest errors.
- Deep-linking to a tab, shareable or persisted chat history.

## 10. Risks and deferred

- **Prompt compliance**: the model may cite sparsely or mis-number; tolerated by design
  (decision 4) - revisit with S8 evaluation data.
- **Large `top_k` overrides** (up to 50) can push the context past free-tier
  tokens-per-minute limits; the failure surfaces as a 502. No truncation mechanism this
  slice.
- **Free-tier 429s**: no auto-retry (decision 7); the user retries manually. Revisit with
  real usage patterns.
- **The canned empty-index answer** is a fixed string; if it later needs per-project or
  per-locale copy, that is a follow-up, not this slice.
