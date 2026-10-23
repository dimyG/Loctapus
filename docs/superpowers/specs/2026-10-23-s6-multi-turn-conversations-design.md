# S6 - Multi-turn conversations + LLM-routed answers - Design

Date: 2026-10-23
Status: Implemented 2026-10-23 on the `s6-multi-turn-conversations` branch (`13f59f1`..`de7922a`,
merge to `master` pending), under `../plans/2026-10-23-s6-multi-turn-conversations.md`. Frozen:
decisions below are as built.
Source of truth: `../../2026-10-06-initial_rag_mvp_agent_project_context.md` (the "MD") and
`2026-10-06-roadmap.md` (the "slices spec"). Where those disagree with this document on S6
topics, this document wins; where this document is silent, they govern.

## 1. Context

S5 froze single-turn answers (its decision 2): every question is self-contained, grounded only
in retrieval, and the UI thread is client-side display history, lost on reload. Its out-of-scope
list named this round: "multi-turn memory or persisted conversations - a later round can add
either behind new interfaces."

This is that round, with the user's scope rulings: conversations are **stored server-side from
the start** (no stateless bridge that a persistence round would later retire), the chat page
**hydrates the owner's latest conversation on mount** so a reload continues the discussion, and
conversations are **personal** (one user + one project). The later round stays display-only:
listing and browsing past conversations.

The core behavior change is the user's routing model: **the LLM decides, before answering,
whether the turn needs retrieval**. Retrieval stops being a reflex and becomes a tool the
router invokes only when the discussion needs it.

Roadmap re-cut (slices spec decision 8): this slice takes the S6 number; the former S6 (real
providers + rerank + API keys + keys UI) shifts to S7.

Done-when (slices spec section 2, S6 row): ask a follow-up question from the browser and get an
answer that resolves against the discussion; reload the page and continue the same discussion.

## 2. Decisions (2026-10-23 design round, user-approved)

1. **Combined scope: persistence now.** The server stores conversations, messages, and cited
   evidence snapshots from day one; `/answer` carries `conversation_id` from day one. No
   transitional client-passed history field.
2. **Personal conversations.** A conversation belongs to one owner inside one project. Only the
   owner can resume or read it; the project visibility check (S4/S5 `get_project_visible_to_user`)
   still gates every route. `user_id` carries no ON DELETE action, the `query_logs` precedent:
   deleting a user must not rewrite a project's discussion past.
3. **Reload continuation now.** `GET .../conversations/latest` hydrates the owner's most recent
   conversation on mount; `POST .../conversations` starts a fresh one ("New chat"). Listing and
   browsing older conversations is the later display round.
4. **The LLM routes before answering** (user's model). One structured router call picks among
   three routes:

   | Route | When | Action |
   |---|---|---|
   | `DIRECT` | Greeting, general conversation, clarification | Answer from the conversation history alone; no retrieval |
   | `REUSE` | The conversation's earlier evidence answers it | Gather this conversation's prior cited chunks (snapshots); answer from history + those |
   | `RETRIEVE` | New information is needed | Rewrite the question standalone using history; retrieve; answer from history + fresh chunks |

5. **Router as a JSON contract, not free-form tool-calls.** The router replies strict JSON
   `{"route": "...", "rewritten_query": "..."}`. No agentic tool-loop (the MD's MVP line).
6. **Router failure degrades, never blocks.** Unparseable JSON, a bad route literal, a blank
   rewritten query on `RETRIEVE`, or a provider error falls back to `RETRIEVE` with the raw
   question - exactly S5's behavior, so the router can never brick the chat. The recorded route
   is the effective one (`retrieve`), never the failed decision.
7. **Max two LLM calls per turn**: router + answer. `DIRECT`/`REUSE` skip embedding and search
   entirely, so conversational turns get cheaper, not costlier.
8. **Evidence snapshots are stored inline.** Each assistant message stores full copies of its
   cited chunk's `text`, `filename`, `heading_path`, and `document_content_hash`, plus a nullable
   live `chunk_id`. Rationale: re-ingestion replaces document and chunk rows, so a live reference
   alone would rot; the inline copy keeps `REUSE` and the hydrated UI working forever. **Staleness
   is known and deferred** (user instruction): a re-ingested document makes old snapshots stale.
   No staleness logic this round - a code comment at the snapshot columns and a
   `docs/backlog.md` entry mark it for a later round.
9. **`query_logs` stays, renamed `retrieve_logs`.** The conversation tables cannot absorb it:
   `/retrieve` still exists on its own (the shifted S7's project API keys authorize exactly
   those programmatic calls, which have no conversation), the snapshot table is deliberately
   lossy (final chunks only), and the S9 evaluation round needs the per-stage candidates,
   settings snapshot, and latency it carries. The rename makes the name match the semantics:
   it logs retrieval calls, not queries.
10. **Only `RETRIEVE` turns retrieve and log.** `params` gains `route` (`direct|reuse|retrieve`),
    `raw_query` (the original question), and `router_fallback` (`true` when the router call
    degraded, so S9 can count router failures). `query` records the rewritten query that was
    actually embedded and searched. The plumbing is a generic `log_context: Mapping[str, str] | None = None`
    parameter on `retrieve()`, merged into `params` - answer-layer concepts stay out of
    `app/retrieval`, and direct `/retrieve` calls simply omit it. `DIRECT`/`REUSE` turns live
    only in the conversation tables. No FK from `retrieve_logs` to conversations - `origin` +
    `route` + `raw_query` is enough traceability for S9; the link is speculative until that
    round asks for it.
11. **Messages, not Q/A pairs.** Role-based rows (`user` | `assistant`) map one-to-one onto the
    provider message list; `position` is unique per conversation; `route` is an assistant-only
    column.
12. **`REUSE` gathers only this conversation's snapshots**, never another conversation's. One
    `gather_snapshots` function: most-recent-first over the conversation's assistant messages,
    deduplicated by `chunk_id`, capped by `answer_reuse_max_chunks`, renumbered `[1..n]` - and
    the same set feeds both the router prompt's evidence summaries and the answer call, so the
    router never decides REUSE because of a passage the answer never receives. A `REUSE`
    decision with zero gathered snapshots degrades to `RETRIEVE` with the raw question (there
    is nothing to reuse, so the honest route is retrieval); the recorded route is the effective
    one (`retrieve`), per decision 6.
13. **Empty-index canned answer stays** for `RETRIEVE` turns that return nothing (no LLM answer
    call). `DIRECT`/`REUSE` work on an empty project: a user can chat before any upload.
14. **One transaction appends a turn**, after both LLM calls succeed: user message + assistant
    message + its snapshots + `last_message_at` bump. The `latest-or-create` conversation row
    is created inside that same transaction - a failed answer call persists nothing, not even an
    empty conversation. `append_turn` locks the conversation row (`SELECT ... FOR UPDATE`) and
    computes `position` as `max + 1` inside the transaction, so concurrent sends cannot collide
    on the unique position. The `retrieve_logs` row written inside `retrieve()` commits earlier
    (S5 decision 10: no open transaction across a remote call), so a turn that dies after
    retrieval leaves a log row for a retrieval that genuinely ran. History reads likewise close
    their transaction before each LLM call.
15. **`conversation_id: null` resolves latest-or-create.** An omitted or null id uses the owner's
    latest conversation in the project, creating one if none exists; an explicit id must be the
    caller's own conversation in this project, else `404 "conversation not found"`. The response
    always returns the resolved id.
16. **The provider interface widens once**, while only two implementations exist:
    `generate(*, system, user)` becomes `generate(*, system, messages)` plus a new
    `route(*, system, messages)`, both over the native OpenAI-compatible message list.

## 3. Data model

One migration (0007) creates three tables and renames one:

```
conversations
  id                  uuid pk
  project_id          FK projects, cascade delete
  user_id             FK users, no ON DELETE action (decision 2)
  created_at          timestamptz, server now()
  last_message_at     timestamptz, non-null, server-default now(), bumped on every
                       append, indexed (decision 15 lookup)

conversation_messages
  id                  uuid pk
  conversation_id     FK conversations, cascade delete
  position            int, unique (conversation_id, position)
  role                text, check in ('user', 'assistant')
  content             text
  route               text, check in ('direct', 'reuse', 'retrieve'); null iff role = 'user'
  created_at          timestamptz, server now()

conversation_message_chunks          # the evidence snapshot table (decision 8)
  id                  uuid pk
  message_id          FK conversation_messages, cascade delete
  ordinal             int, unique (message_id, ordinal)   # citation order [1]..[n]
  chunk_id            uuid, FK chunks ON DELETE SET NULL, indexed   # null once re-ingestion
                                                                # replaces the cited chunk
  filename            text
  heading_path        jsonb
  text                text                              # durable inline snapshot
  document_content_hash  text                           # version marker of the cited document

retrieve_logs                         # renamed from query_logs (decision 9); columns unchanged
```

- The `last_message_at` index is `(project_id, user_id, last_message_at)`; `user_id` additionally
  gets its own index per the repo's explicit-FK-index convention (0004), and `chunk_id` gets one
  because it is a real foreign key (`test_foreign_key_columns_are_indexed`). The messages/chunks
  uniques lead with their FK column, so they serve the FK lookups. `last_message_at` is non-null
  from creation (server default `now()`), so the `ORDER BY ... DESC` latest lookup never sorts
  nulls; `GET .../conversations/latest` on a just-created empty conversation returns `200` with
  `messages: []`.
- `conversation_message_chunks` carries the staleness comment (decision 8, user instruction)
  at the snapshot columns in `app/conversations/models.py`.

## 4. API contract

```
POST /api/projects/{project_id}/answer                      (JWT, changed)
  { "query": "...",                                       // QueryText rules unchanged
    "conversation_id": null,                              // null/omitted -> latest-or-create
    "top_k": null, "rerank": false,
    "max_chunks_per_document": null }                     // override semantics unchanged (S5)
  200 ->
  { "answer": "...",
    "route": "direct" | "reuse" | "retrieve",
    "conversation_id": "<uuid>",                          // the resolved id (decision 15)
    "chunks": [ SnapshotChunkOut ] }                      // [n] order; [] on DIRECT and empty RETRIEVE

POST /api/projects/{project_id}/conversations               (JWT, new - "New chat")
  201 -> { "conversation_id": "<uuid>" }                    # empty conversation, owned by the caller

GET /api/projects/{project_id}/conversations/latest         (JWT, new - hydrate on mount)
  200 -> { "conversation_id": "<uuid>",
           "messages": [ { "role": "user" | "assistant",
                           "content": "...",
                           "route": ...,                   # assistant rows only
                           "chunks": [ SnapshotChunkOut ] } ] }   # ordered by position
  200 -> { "conversation_id": "<uuid>", "messages": [] }     # a just-created empty conversation
  404 -> the caller owns no conversation in this project

SnapshotChunkOut = { "chunk_id": uuid | null, "filename": str,
                     "heading_path": [str], "text": str,
                     "document_content_hash": str }
```

- `AnswerOut.chunks` becomes `SnapshotChunkOut` uniformly across routes: what the UI renders
  (filename, heading path, text) plus provenance. `score`, `position`, `document_id`,
  `source_item_id`, and `chunk_type` drop from the answer response - none are displayed, and the
  snapshot table does not store them. `/retrieve`'s `RetrievedChunkOut` is unchanged.
- `404 "project not found"` semantics unchanged (visibility check first, then the conversation
  ownership check); `401`/`422` unchanged; `502` on answer-call failure with the provider's
  user-safe copy (S5 decisions 10). A router failure never yields 502 - it falls back (decision 6).
- `POST .../conversations` on an invisible project is `404 "project not found"`, same gate.

## 5. Per-turn flow

```
POST /api/projects/{project_id}/answer (JWT, conversation_id?)
  -> get_project_visible_to_user (404 as today)
  -> resolve conversation: null -> latest-or-create; explicit -> owned or 404
  -> load history (last answer_history_messages messages) + gather_snapshots (the
     REUSE set, decision 12) for the router prompt; the read transaction closes
     before any LLM call (decision 14)
  -> ROUTER call (system + history + evidence summaries + new question)
       DIRECT   -> answer call: conversational system + history + question
       REUSE    -> gather_snapshots (decision 12): most-recent-first, deduped,
                    capped, renumbered [1..n];
                    none? -> degrade to RETRIEVE with the raw question;
                    answer call: grounded system + history + question + snapshot blocks
       RETRIEVE -> effective query = rewritten_query or the raw question;
                    retrieve(effective_query, origin="answer") -> retrieve_logs row;
                    no chunks? -> canned answer, no answer call;
                    answer call: grounded system + history + question + fresh blocks
  -> one transaction: conversation creation (null case) + user message + assistant
     message (route, answer) + snapshot rows (REUSE gathered / RETRIEVE fresh)
     + last_message_at bump
  -> 200 { answer, route, conversation_id, chunks }
```

- `generate_answer` orchestrates; `app/conversations` owns persistence; `retrieve()` stays
  untouched inside `app/retrieval` except the log rename and the `log_context` parameter
  (decision 10). History reads commit before each LLM call, and the conversation row insert
  happens in the final append transaction (decision 14).
- The answer prompt's final user message keeps S5's `Question:` + numbered-blocks shape; the
  trimmed history rides ahead of it as chat messages. Citation `[n]` instructions and tolerance
  are unchanged (S5 decisions 4 and 11).

## 6. Provider, prompts, settings

**Provider** (`app/providers/base.py`):

```
ChatMessage    = dataclass { role: Literal["user", "assistant"], content: str }
RouteDecision  = dataclass { route: Literal["direct", "reuse", "retrieve"],
                             rewritten_query: str | None }   # None -> use the raw question

class LLMProvider(Protocol):
    def route(*, system: str, messages: list[ChatMessage]) -> RouteDecision: ...
    def generate(*, system: str, messages: list[ChatMessage]) -> str: ...
```

- **Stub**: `route()` returns `RouteDecision(route="retrieve", rewritten_query=None)` - so the
  offline dev path keeps today's retrieval behavior; `generate()` returns the fixed `[1]` answer.
- **Groq**: both calls hit `/chat/completions` through one shared `_complete(messages,
  max_tokens, timeout_seconds)` helper; the router call uses `llm_route_max_tokens` +
  `llm_route_timeout_seconds`, the answer call `llm_max_tokens` + `llm_timeout_seconds`.
  Router reply parsing is defensive: non-JSON, a bad route literal, or a
  missing/blank rewritten query on `retrieve` raise `LLMError`, which the service turns into the
  fallback (decision 6). No `response_format` request field - prompt for strict JSON and parse.

**Prompts** (`app/answers/prompt.py` grows):

- `ROUTER_SYSTEM_PROMPT`: the three-route semantics from decision 4's table, strict-JSON
  instructions, and "prefer RETRIEVE when unsure".
- `build_route_messages(question, history, evidence)`: trimmed history, then the gathered
  evidence (decision 12's `gather_snapshots` set, truncated per passage by a module constant),
  then the question - the same set the answer call reuses, so the router's REUSE judgment is
  honest (decision 12).
- `SYSTEM_PROMPT_DIRECT`: answer the question from the conversation history; no context passages
  are supplied; be concise.
- `SYSTEM_PROMPT` (grounded): today's wording, unchanged.
- `build_user_prompt` keeps its shape for the final message; snapshot chunks and fresh
  `RetrievedChunk` both render as `[n] filename - heading` blocks.

**Settings** (`app/core/config.py` grows):

| Setting | Default | Validation |
|---|---|---|
| `answer_history_messages` | `6` | `>= 1` |
| `answer_reuse_max_chunks` | `10` | `>= 1` |
| `llm_route_max_tokens` | `128` | `> 0` |
| `llm_route_timeout_seconds` | `10` | `> 0` |

`llm_provider`, `groq_*`, `llm_timeout_seconds` (the answer call), `llm_max_tokens`,
`answer_context_chunks`, and `answer_max_chunks_per_document` are unchanged. The split router
timeout keeps the worst-case turn - a 10s router call plus a 30s answer call plus embedding and
search - inside nginx's 60s `proxy_read_timeout`, so failures surface as the friendly 502
(S5 decision 12's guarantee), never an nginx 504.

## 7. Frontend design

`web/src/features/chat/answersApi.ts`:

- `askQuestion` body gains `conversation_id: string | null`; the response type gains `route` +
  `conversation_id` and swaps `chunks` to the `SnapshotChunk` shape (`chunk_id: string | null`).
- New: `getLatestConversation` query (`{ conversation_id, messages }` or 404) and
  `createConversation` mutation (`-> { conversation_id }`).

`web/src/features/chat/ChatPanel.tsx`:

- On mount, fetch latest: `200` -> map message pairs into turns (user position + its assistant
  reply), `404` -> empty thread, `conversation_id = null`.
- `conversationId` state rides every send; a successful ask adopts the response's
  `conversation_id` (covers the null -> created case).
- **New chat** button (top of the thread): `createConversation`, reset turns, adopt the new id.
- `SourcesChips` keys and dialog state use the array index (snapshot `chunk_id` can be null or
  repeat when REUSE re-gathers a chunk); the dialog flow is otherwise unchanged. Pending,
  error card, and Try again are unchanged.
- `askQuestion` and `createConversation` invalidate the `getLatestConversation` cache tag, so
  revisiting the page never shows a stale thread.
- `ChatPage.tsx`, `ChatLanding.tsx`, and the `/app` resolver are untouched.

## 8. Module layout

```
backend/
  app/
    conversations/                  # new: conversation persistence
      __init__.py
      models.py                     # Conversation, ConversationMessage, ConversationMessageChunk
      schemas.py                    # SnapshotChunkOut, MessageOut, ConversationOut
      service.py                    # create, get_latest, get_owned, append_turn, gather_snapshots
      router.py                     # POST /conversations, GET /conversations/latest
    answers/
      schemas.py                    # AnswerIn + conversation_id; AnswerOut + route/conversation_id
      prompt.py                     # router prompts, conversational system, message-list builders
      service.py                    # route -> three paths -> append_turn
      router.py                     # unchanged shape
    providers/
      base.py                       # ChatMessage, RouteDecision; protocol: route + generate
      stub_llm.py                   # + route()
      groq_llm.py                   # + route(), shared _complete with per-call timeout
      __init__.py                   # factory passes llm_route_max_tokens/timeout
    retrieval/
      models.py                     # QueryLog -> RetrieveLog, table retrieve_logs, index renames
      service.py                    # + log_context into params; RetrievedChunk gains
                                     #   document_content_hash (enrich join)
    main.py                         # + conversations router include
  alembic/versions/0007_conversations.py
tests/
  providers/test_groq_llm.py       # extended: route() payloads and error mapping
  providers/test_stub_llm.py       # extended: route() determinism
  answers/test_prompt.py           # extended: router + direct + message-list builders
  answers/test_service.py           # the three routes, fallbacks, persistence transaction
  answers/test_answer_api.py       # contract: shapes, 404s, 502, canned empty
  conversations/                   # new: service + router tests (latest, ownership, append)
web/src/features/chat/             # per section 7
```

Import directions: `answers` -> `conversations`, `retrieval`, `providers`; `conversations` ->
core models only. Nothing imports `answers`. `main.py` mounts the conversations router.

## 9. Migration (0007)

- `ALTER TABLE query_logs RENAME TO retrieve_logs`; rename
  `ix_query_logs_project_id_created_at` -> `ix_retrieve_logs_project_id_created_at` and
  `ix_query_logs_user_id` -> `ix_retrieve_logs_user_id` (Postgres keeps index names when a
  table is renamed, so the explicit renames keep the ORM names honest). Rows are preserved.
- Create `conversations`, `conversation_messages`, `conversation_message_chunks` per section 3,
  with the checks, uniques, and FK indexes described there.
- Downgrade reverses all four operations. ORM model `QueryLog` becomes `RetrieveLog`
  (`__tablename__ = "retrieve_logs"`).

## 10. Testing approach

- **Providers, hermetic**: stub `route()` determinism (`RETRIEVE`, `rewritten_query=None`);
  Groq `route()` via `httpx.MockTransport` - valid JSON -> `RouteDecision`; garbage JSON, bad
  route literal, blank rewritten query, 429/5xx/timeout -> `LLMError`; both payloads carry
  model, bearer, messages, and their own `max_tokens`. `generate()` over the messages list
  keeps today's tests.
- **Service, real Postgres + seeded chunks + fake routing provider**: each route end-to-end;
  `DIRECT`/`REUSE` write no `retrieve_logs` row; `RETRIEVE` logs `params.route` +
  `params.raw_query` (+ `router_fallback` on the fallback) with the rewritten `query`;
  router `LLMError` -> fallback `RETRIEVE` raw; `REUSE` with zero snapshots -> `RETRIEVE` raw;
  `gather_snapshots` caps most-recent-first, dedupes, and renumbers; the turn persists
  (user + assistant + snapshots + `last_message_at`) in one transaction, and a failed answer
  call persists nothing, not even the `latest-or-create` conversation; concurrent `append_turn`
  calls serialize through the row lock (positions 1 and 2, no IntegrityError); foreign /
  cross-project conversation -> 404-shaped miss; null id -> latest-or-create.
- **Answer API**: 200 shape (`answer`, `route`, `conversation_id`, `chunks` as snapshots); 401;
  project 404; conversation 404; 422 bounds unchanged; empty-index `RETRIEVE` -> canned answer,
  `route: "retrieve"`, `[]`; answer-call failure -> 502; `rerank: true` still accepted.
- **Conversations API**: `POST` 201 + ownership; `GET latest` 200 messages-in-order with per
  message snapshot chunks; 404 when the caller owns none; another user's conversation is
  invisible.
- **Existing tests**: every `query_logs`/`QueryLog` assertion updates for the rename.
- **Frontend (vitest + MSW)**: hydration renders prior turns and their sources from snapshots;
  404 -> empty thread; New chat resets and the next ask carries the new id; ask adopts the
  response `conversation_id`; null-`chunk_id` source chips do not collide.
- **Playwright e2e**: the journey extends past ask - reload, the thread is still there
  (hydrated), ask a follow-up, the stub answer renders again. The stub always routes
  `RETRIEVE` with a fixed answer, so the follow-up-resolves-against-the-discussion half of
  done-when is verified by a **manual Groq check** (`RAG_LLM_PROVIDER=groq`): ask, then ask a
  follow-up that only makes sense with history, and confirm the answer resolves it.
- Full gate per AGENTS.md: `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest`,
  plus the web `vitest`/`eslint` gate.

## 11. Out of scope (recorded, not built)

- The display round: listing and browsing older conversations, deep links, sharing.
- Streaming (S5 rejection stands).
- A dedicated condense/rewrite call - the router's `rewritten_query` covers the MVP need; a
  standalone rewrite step can slot in behind `LLMProvider` if S9 evaluation shows follow-up
  retrieval failing.
- Snapshot staleness detection or re-validation (decision 8; backlog).
- `retrieve_logs` -> conversations FK (decision 10).
- Cross-conversation `REUSE`; multi-user or shared conversations.
- The shifted S7: real providers, rerank activation, API keys + keys UI.
- Token-usage accounting; per-conversation settings.

## 12. Risks and deferred

- **Router latency**: every turn pays one extra LLM call, bounded by `llm_route_max_tokens`
  (128) and `llm_route_timeout_seconds` (10s). The worst-case turn budget - 10s router + 30s
  answer + embedding and search - stays inside nginx's 60s `proxy_read_timeout`, so failures
  surface as the friendly 502, never an nginx 504.
- **Router mis-judgment**: the fallback only catches failures, not bad routing (e.g. `DIRECT`
  chosen for a question that needed evidence). Revisit with S9 evaluation data over
  `retrieve_logs.params.route`.
- **History dilution**: a rewritten query still embeds as one vector; long discussions can
  drift. Bounded by `answer_history_messages` (6).
- **`[n]` renumbering in history**: history messages carry the earlier turns' `[n]` citation
  markers, whose numbers no longer match the new turn's context blocks and can confuse the
  model. A cheap mitigation - stripping or rewriting markers in the history passed to the
  model - is decided at implementation.
- **Snapshot staleness** (user-flagged, decision 8): reloading an old conversation after
  re-ingestion cites superseded text as if current. Deferred by explicit instruction - code
  comment + backlog entry.
- **Storage growth**: snapshots duplicate chunk text per citation. Chunk texts are small
  (500-700 tokens) and per-message citations are capped; acceptable for MVP, revisit with the
  display round.