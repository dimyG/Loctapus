# RAG MVP — Project Context for Implementation Agent

## 1. Project purpose

Build an MVP of a Kapa.ai-like ingestion and retrieval service.

The core idea is to turn a project's source material into a searchable knowledge base that an AI assistant or another agent can query. The retrieval layer is the core product: it should return the most relevant grounded chunks, ranked and linked back to their source. Answer generation is a separate layer built on top of retrieval.

The system has two main flows:

1. **Offline / asynchronous ingestion and indexing**
   - ingest source content
   - parse and normalize it
   - split it into chunks
   - create lexical and vector indexes
   - keep the indexed representation synchronized with the source

2. **Online / synchronous retrieval**
   - accept a user query
   - generate its embedding
   - run lexical and vector retrieval
   - fuse candidate rankings
   - rerank candidates
   - apply diversity/final selection
   - return grounded chunks
   - optionally pass those chunks to an LLM through `/answer`

The MVP should be production-shaped, but not production-complex. Prefer simple architecture with clean boundaries that can be separated or replaced later.

---

## 2. Current MVP scope

### Included

- User registration and login.
- JWT authentication.
- Project-based knowledge bases.
- PDF/DOCX upload as the first source type.
- Source ingestion status tracking.
- Parsing and normalization into a common document representation.
- Structure-aware recursive chunking.
- Embeddings for chunks.
- PostgreSQL full-text search for lexical retrieval.
- pgvector + HNSW for semantic retrieval.
- Reciprocal Rank Fusion (RRF).
- Hosted reranking.
- `/retrieve` endpoint.
- `/answer` endpoint using retrieved passages.
- Raw source storage in S3/MinIO.
- Asynchronous ingestion with Celery + RabbitMQ.
- Transactional outbox.
- Query logging sufficient for future retrieval evaluation.
- Basic web UI using Devias Kit / React / Redux / Next.js.

### Explicitly not required for the first MVP

- Website ingestion. This comes after PDF/DOCX.
- Agentic/deep retrieval loops.
- Query rewriting/decomposition.
- Image understanding/captioning.
- Dedicated vector database.
- Elasticsearch/OpenSearch/BM25 infrastructure.
- Multiple worker services.
- Teams/invitations/permission management in the UI.
- Complex document-level ACLs.
- Historical source versions in the active retrieval index.

---

## 3. High-level architecture

```text
Clients
  |
  +-- Web UI
  +-- REST API
  |
  v
Application/API service
  |
  +-- identity/account
  +-- projects
  +-- sources
  +-- /retrieve
  +-- /answer
  |
  +-----------------------------+
  |                             |
  | synchronous query path      | asynchronous ingestion path
  |                             |
  v                             v
Query pipeline               RabbitMQ
  |                             |
  |                          Celery worker
  |                             |
  |                        parse / normalize
  |                             |
  |                           chunk
  |                             |
  |                           embed
  |                             |
  +-------------+---------------+
                |
                v
      PostgreSQL + pgvector
      - relational data
      - FTS / GIN index
      - embeddings / HNSW index

Raw uploaded files -> S3 / MinIO
```

For the MVP, keep the main application components in one service, but make retrieval a clean internal module/boundary so it can later become its own service.

---

## 4. Core domain model

The current conceptual hierarchy is:

```text
Project
  -> Source
    -> SourceItem
      -> Document
        -> Chunk
```

### Project

A project is the logical knowledge base and retrieval boundary.

A user may have multiple projects.

Every important data record should be scoped by `project_id` where applicable.

### Source

A source is the configured external source or uploaded source container.

For the MVP, the initial source type is PDF/DOCX upload.

Later, a website source may represent an entire documentation site.

### SourceItem

A SourceItem is one concrete item discovered inside a Source.

Examples:

- uploaded-file source -> one uploaded file
- website source -> one webpage
- Google Drive source -> one Drive document

### Document

A Document is the application's normalized representation of one parsed state of a SourceItem.

The SourceItem is the stable identity of the uploaded/external item. If that item changes and is reparsed, a replacement Document is created.

For the MVP, only the current Document needs to remain active for retrieval. Do not delete the old active Document and its chunks until the replacement has been parsed, chunked, embedded and indexed successfully. Once the replacement is ready, the previous Document and its chunks may be deleted.


### Chunk

A Chunk is the searchable retrieval unit derived from a normalized document.

Each chunk should retain enough metadata to trace it back to its source and position.

Example:

```json
{
  "heading_path": ["Authentication", "Python SDK"],
  "document_id": "...",
  "url": "...",
  "position": 7
}
```

Future-ready chunk types may include:

- text
- code
- table
- image_caption

Image captions are not part of the first MVP.

---

## 5. Normalized document representation

All source formats should converge on a common internal document model.

Example:

```json
{
  "document_id": "...",
  "project_id": "...",
  "source_item_id": "...",
  "title": "Authentication",
  "elements": [
    {
      "type": "heading",
      "level": 1,
      "text": "Authentication"
    },
    {
      "type": "paragraph",
      "text": "..."
    }
  ],
  "metadata": {
    "url": "...",
    "updated_at": "..."
  }
}
```

The normalized representation should preserve semantic structure such as headings, paragraphs, code blocks and tables rather than flattening everything immediately into unstructured text.

Everything after parsing should work against this common format rather than against source-specific formats.

---

## 6. Ingestion pipeline

The intended ingestion flow is:

```text
raw source
  -> parse
  -> normalize document structure
  -> chunk
  -> persist chunks
  -> publish "document ready for embedding"
  -> embed chunks in batches
  -> save vectors
  -> PostgreSQL indexes update
  -> mark document/source ready
```

The user-facing flow is approximately:

```text
POST /sources
  -> create source
  -> enqueue ingestion
  -> return source_id + status
```

Suggested status values:

- queued
- fetching
- processing
- indexing
- ready
- failed

Internally, more granular statuses may be used.

For the first PDF/DOCX connector, fetching means receiving/storing the uploaded file rather than crawling a remote system.

---

## 7. Parsing

Initial source type:

- PDF
- DOCX

Use the **Unstructured hosted API** as the parsing technology for the MVP because it can partition documents into structured elements such as titles, narrative text, lists and tables, while avoiding the operational overhead of running the parsing stack locally.

Current MVP choice:

- **Unstructured hosted API**
- use the free allowance first
- parsing happens remotely through the API
- uploaded raw files are still stored in our own S3/MinIO before parsing

The parser must remain behind an abstraction so that the implementation can later switch to:

- local/open-source Unstructured
- another hosted parser
- another parser implementation

Do not let Unstructured-specific response objects become the application's domain model. Convert the provider response into the common normalized document format immediately after parsing.

---

## 8. Raw source storage

Store the raw source before parsing.

Use S3-compatible object storage, such as MinIO locally.

Purpose:

- reparsing without asking the original source again;
- reproducibility;
- debugging parser behavior;
- future parser upgrades.

A document should keep an object key such as `raw_object_key`.

---

## 9. Chunking

For the MVP use **structure-aware recursive chunking**.

Preferred hierarchy:

```text
document
  -> section
    -> subsection
      -> paragraph
        -> sentence/token fallback
```

Use semantic structure first and hard token boundaries only when necessary.

Initial tuning values:

- target: ~500–700 tokens
- maximum: ~1000 tokens
- overlap: ~80 tokens

These are defaults, not architectural constants.

The chunking strategy must be replaceable because different source types may eventually need different chunking logic.

---

## 10. Embeddings

Use a hosted embedding provider behind an interface similar to:

```python
class EmbeddingProvider:
    def embed_documents(self, texts):
        ...

    def embed_query(self, text):
        ...
```

Document and query embeddings must use compatible representations from the same embedding model/provider configuration.

Batch document embeddings aggressively. Do not send one chunk per API request when batching is possible.

Current cost-first provider choice:

- **Voyage AI**
- document embeddings: `voyage-4-lite`
- query embeddings: `voyage-4-lite`
- use the provider's document/query input modes where appropriate

---

## 11. Indexing and storage

For the MVP use one PostgreSQL database for relational data, lexical search and vector search.

### Vector retrieval

- pgvector
- HNSW index
- cosine similarity/distance unless there is a reason to use another metric

### Lexical retrieval

Use PostgreSQL Full Text Search:

- `tsvector`
- `tsquery`
- `ts_rank`
- GIN index

Important: PostgreSQL FTS ranking is **not BM25**.

True BM25 / OpenSearch / dedicated lexical infrastructure may be introduced later if needed.

### Chunk storage

The chunk table needs fields approximately like:

```text
id
project_id
document_id
position
text
heading_path
chunk_type
metadata
content_hash
embedding
search_vector
```

PostgreSQL automatically maintains the HNSW and GIN indexes as chunk rows/vectors/search vectors are inserted or updated.

---

## 12. Retrieval pipeline

The query path must be synchronous and low latency, and conceptually separate from ingestion.

Endpoint:

```text
POST /projects/{id}/retrieve
```

Parameters include at least:

- query
- top_k, default around 10
- rerank, configurable true/false
- max_chunks_per_document

Pipeline:

```text
user query
  -> embed query
  -> vector search
  -> FTS search
  -> RRF
  -> rerank
  -> diversity / final selection
  -> return chunks
```

Do not add query normalization/rewrite/decomposition to the first MVP.

---

## 13. Initial retrieval quantities

A good initial default from the design notes is:

- retrieve roughly 30–100 candidates from each retriever;
- combine vector and lexical rankings using RRF;
- send roughly the best 20–50 fused candidates to the reranker;
- select around the final top 10 chunks.

These values should be configuration, not hard-coded business rules.

---

## 14. Reciprocal Rank Fusion

Use RRF to combine lexical and vector rankings.

RRF should combine based on rank position rather than attempting to directly compare incompatible raw scores from pgvector and FTS.

Conceptually:

```text
RRF_score(item) =
    1 / (k + lexical_rank)
  + 1 / (k + vector_rank)
```

---

## 15. Reranking

Reranking is a second-stage relevance pass over the candidate set.

It should be configurable:

```text
rerank = true | false
```

Current cost-first provider choice:

- **Voyage AI**
- `rerank-3-lite`

Add a `max_chunks_per_document` option so the final context is not dominated by many similar chunks from one document.

If the hosted reranker does not support this directly:

1. rerank all fused candidates;
2. apply local diversity filtering afterward;
3. select the final top results.

---

## 16. `/retrieve` and `/answer`

Keep retrieval and answer generation separate.

### `/retrieve`

The retrieval endpoint should be useful on its own and should return grounded passages and source metadata.

It must not require customers to use the system's LLM.

### `/answer`

Flow:

```text
user question
  -> call retrieval internally
  -> receive final relevant chunks
  -> build grounded LLM context
  -> call LLM
  -> return answer
```

The LLM should be instructed to answer from the supplied context.

Current cost-first provider choice:

- **Groq**
- `openai/gpt-oss-20b`

Provider access must be abstracted so that OpenAI or another LLM can replace it later.

---

## 17. Asynchronous workers and queues

Technology:

- Celery
- RabbitMQ

For the MVP, one Celery worker may consume all tasks.

Queues:

- `ingestion`
- `embed`

For the MVP:

- sync/fetch + parse/chunk may share the `ingestion` queue;
- embedding uses the `embed` queue.

The architecture should allow these workloads to be split across workers later without redesigning the ingestion model.

For PDF/DOCX-only MVP, "sync" is minimal compared with future remote sources, but preserve the same conceptual ingestion contract.

---

## 18. Transactional outbox

Use the transactional outbox pattern in the MVP.

The outbox is a **dedicated database table** (`outbox_events`), not a field on `documents`, `chunks` or `ingestion_runs`.

Example:

1. parsing/chunking produces a Document and chunks;
2. in one PostgreSQL transaction:
   - save/update the Document;
   - save its chunks;
   - insert an `outbox_events` row such as `document_ready_for_embedding` with the `document_id`;
3. commit;
4. a small dispatcher polls unpublished outbox rows;
5. it publishes each event/task to RabbitMQ;
6. after successful publish, it marks `published_at`;
7. the embedding worker consumes the message.

Example table:

```text
outbox_events

id
event_type             # e.g. document_ready_for_embedding
aggregate_type         # e.g. document
aggregate_id           # e.g. document id
payload                 # JSON/JSONB event/task payload
created_at
published_at            # null until successfully published
attempts                # publisher retry count
last_error              # last publish error, if any
```

The dispatcher may initially poll roughly every second.

A crash can happen after publishing to RabbitMQ but before setting `published_at`, so the same event can occasionally be published twice. That is expected. Consumers must therefore be idempotent.

Do not treat a database commit plus a separate broker publish as one atomic operation; the outbox exists to bridge that gap reliably.


---

## 19. Idempotency

Ingestion must be idempotent.

Conceptually:

```text
ingest(source_item X, version Y)
```

must be safe to execute more than once.

A uniqueness rule can use something like:

```text
(source_item_id, content_hash)
```

If the same version/content is already processed, the operation should become a no-op rather than duplicate data.

This is required because Celery/message delivery may be at-least-once.

---

## 20. Synchronization

Use **polling** for synchronization in the MVP.

A scheduler such as Celery Beat periodically enqueues `SyncSource(source_id)` according to `sources.sync_interval`. Each connector checks whether its SourceItems changed and only reprocesses changed items.

Initial ingestion and later synchronization should reuse essentially the same connector logic.

Change detection depends on source type:

- uploaded/local file: content hash / mtime where applicable
- future website: ETag / Last-Modified / normalized-content hash
- future Git source: commit SHA
- future APIs: `updated_at`, revision/version or cursor/change feed

Webhooks/change feeds may supplement or replace polling later, but they are not part of the MVP.

When a source changes, keep the old Document/chunks available until the replacement Document has been successfully parsed, chunked, embedded and indexed. Then remove the stale Document/chunks.


---

## 21. Connector abstraction

All source connectors should expose roughly the same responsibilities:

```python
discover(...)
fetch(...)
```

Everything after `fetch()` should stop caring whether the source came from PDF, DOCX, website, GitHub, Slack, etc.

For the MVP, only PDF/DOCX is required.

Later website support should follow approximately:

```text
sitemap.xml
  -> discover URLs
  -> HTTP fetch
  -> HTML extraction
  -> normalized document
```

For JS-heavy sites, use browser rendering only as a fallback because Chromium/Playwright is significantly more expensive than normal HTTP fetching.

---

## 22. Users, workspace, teams and permissions

The long-term model in the notes is:

```text
Organization
  has exactly one owner User

Team
  belongs to exactly one Organization

User <-> Team
  many-to-many

Project
  belongs to exactly one Organization

Project <-> Team
  many-to-many
  role: admin | editor | viewer

User <-> Project
  no direct relationship

User <-> Organization
  no general membership relationship
  only direct relationship is ownership

Public project
  is_public = true
  all application users may query it
```

Default registration behavior in the long-term model:

- create a personal organization/workspace;
- create a personal team;
- add the user to that team;
- new projects are attached to that personal team.

### MVP simplification

Create the underlying model so the system does not need to be redesigned later, but initially support only a single-user flow:

- one user;
- one default workspace/organization;
- one default team;
- projects;
- no team management UI;
- no invitations;
- no role assignment UI;
- no complex permission management.

The notes use both "workspace" and "organization". Prefer **workspace** in the product/UI language unless the data model already uses `organization`.

---

## 23. Authentication and API keys

Use **JWT** for human users interacting with the web application.

```text
register/login
  -> issue JWT
  -> browser sends JWT with authenticated application requests
```

Use **API keys** for programmatic access to `/retrieve`, so users can call the retrieval service from their own applications and use the returned chunks with their own LLM instead of `/answer`.

For the MVP, API keys are **project-scoped** rather than user-scoped. A valid key authorizes access to one project's knowledge base. Allow multiple keys per project so users can have separate development, production or integration keys and rotate/revoke them independently.

Suggested table:

### api_keys

```text
id
project_id
name
key_prefix              # short non-secret prefix displayed for identification
key_hash                # store only a secure hash; never store the raw secret
created_by_user_id
scope                   # MVP: retrieve
created_at
last_used_at
revoked_at
```

Creation flow:

```text
logged-in user (JWT)
  -> POST /projects/{project_id}/api-keys
  -> server generates a high-entropy secret
  -> raw key is shown once
  -> only the hash and metadata are persisted
```

Programmatic retrieval:

```text
customer application
  -> POST /projects/{project_id}/retrieve
  -> X-API-Key: <secret>
  -> validate key
  -> verify project + scope + revocation state
  -> execute retrieval
  -> attribute usage to api_key_id/project_id
```

Suggested endpoints:

```text
POST   /projects/{project_id}/api-keys
GET    /projects/{project_id}/api-keys
DELETE /projects/{project_id}/api-keys/{key_id}
```

Usage, rate limiting and future billing should be attributable at least to `api_key_id` and `project_id`.


---

## 24. UI

Use:

- Devias Kit
- React
- Redux
- Next.js

MVP UI should support:

- landing page describing the problem/solution;
- register/login;
- project list/dropdown;
- create project;
- project page;
- upload PDF/DOCX source;
- view source processing status;
- delete source;
- ask questions against the project;
- display the answer in a simple AI-chat style.

Future UI ideas in the notes, but not required in the single-user MVP:

- invitations;
- per-project roles;
- public projects;
- richer workspace/team administration.

---

## 25. Current external providers

Cost-first choices currently recorded in the project notes:

| Need | Provider / model |
|---|---|
| PDF/DOCX parsing | **Unstructured hosted API** |
| Document embeddings | Voyage AI `voyage-4-lite` |
| Query embeddings | Voyage AI `voyage-4-lite` |
| Reranking | Voyage AI `rerank-3-lite` |
| `/answer` generation | Groq + `openai/gpt-oss-20b` |

Guiding principle: choose free plans first for the MVP and keep provider interfaces replaceable.

---

## 26. Draft API areas

### Identity / account

```text
/register
/login
/users
```

### Project / source management

```text
/projects
/projects/{id}/sources
/projects/{id}/api-keys
```

### Query

```text
/projects/{id}/retrieve
/projects/{id}/answer
```

Exact REST details are still open for implementation planning.

---

## 27. Draft persistence model

Current notes identify these core tables.

### projects

```text
id
name
```

### sources

```text
id
project_id
type
config                 # source-type-specific JSON/JSONB settings
                       # e.g. future website root_url/use_sitemap
status                 # overall ingestion state:
                       # queued | fetching | processing | indexing | ready | failed
sync_interval          # polling interval for MVP synchronization
last_sync_at
```

### source_items

```text
id
source_id
external_id            # stable identifier for the item inside the source:
                       # upload id, canonical URL, Drive file id, etc.
url
remote_version         # provider/source version marker when available:
                       # ETag, revision, commit SHA, etc.
content_hash
last_seen_at           # last poll in which the item was confirmed to exist;
                       # useful for detecting remote deletions
deleted_at
```

### documents

```text
id
source_item_id
content_hash            # identifies parsed content for idempotency/change detection
raw_object_key          # key/path of the original uploaded file in S3/MinIO
normalized_content      # common parsed document representation
created_at
```

### chunks

```text
id
project_id             # INTENTIONAL DENORMALIZATION for the retrieval hot path.
                       # Avoids joining chunk -> document -> source_item -> source
                       # for every project-scoped vector/FTS query.
                       # Add this rationale as a comment in the code/model too.
document_id             # owning normalized Document
position                # chunk order within the Document
text                    # text used for retrieval/reranking
heading_path            # hierarchy of enclosing headings, e.g.
                       # ["Deployment", "Kubernetes", "Authentication"]
chunk_type              # text | code | table | image_caption
metadata                # source/citation metadata needed at retrieval time
content_hash            # supports idempotency/change detection
embedding               # pgvector dense semantic embedding
search_vector           # PostgreSQL tsvector for lexical full-text search
```

### ingestion_runs

Each row records one ingestion/synchronization execution. This is durable application workflow/history state; RabbitMQ/Celery remain the transport/execution mechanism.

```text
id
source_id
document_id            # nullable until the run produces a Document
status                 # queued | fetching | processing | indexing | ready | failed
attempt                 # retry/attempt number
started_at
finished_at
error
```

### outbox_events

Generic application outbox table used by the transactional outbox pattern.

This is a shared table for all events/messages that must be published reliably after a database transaction commits. It is not limited to ingestion events.

Examples:

```text
document_ready_for_embedding
source_deleted
source_updated
project_deleted
api_key_revoked
```

Schema:

```text
id
event_type             # event/message name, e.g. document_ready_for_embedding
aggregate_type         # entity type the event concerns, e.g. document, source, project
aggregate_id           # id of that specific entity
payload                 # JSON/JSONB event/task payload
created_at
published_at            # null until RabbitMQ publish succeeds
attempts                # publisher retry count
last_error              # last publishing error, if any
```

Example:

```text
event_type     = document_ready_for_embedding
aggregate_type = document
aggregate_id   = doc_123
```

The outbox dispatcher reads rows where `published_at IS NULL`, publishes them to the appropriate RabbitMQ queue/routing key based on `event_type`, and then marks them as published.

### query_logs

For the MVP, persist both intermediate and final retrieval outputs so queries can be debugged and later labeled for evaluation.

```text
id
project_id
query
latency_ms
fts_result_ids
vector_result_ids
final_result_ids
fts_scores
vector_scores
rerank_scores
created_at
```

This schema is a draft and should be normalized/refined during implementation planning.

---

## 28. Retrieval evaluation

Do not evaluate the MVP only by whether generated answers "look good".

Retrieval quality must be measured directly.

Initial metrics:

### Recall@K

Measures how many relevant chunks were found in the top K results.

```text
Recall@K =
relevant chunks found in top K
/
total relevant chunks
```

### MRR

Mean Reciprocal Rank measures how high the first relevant result appears.

Examples:

```text
first relevant result at rank 1 -> 1.00
rank 2 -> 0.50
rank 5 -> 0.20
```

Store enough query/retrieval data to later turn real queries into labeled evaluation examples.

---

# 29. Existing guidelines — preserve as written

- Design the code in a way that it is very easy to switch external api providers later. For example for reranking, source connectors, LLM, embeddings etc.
- Always choose the free plan first. 
- For the web UI use devias kit (react, redux, next)
- For MVP start with all main components on one common service but design with the intension to separate /retrieval to a different service later.
- For authentication use jwt.
- we create the underlying Users model structure but in the MVP we only have single users (with single workspace, team). No need for creating teams, inviting users, assigning permissions yet.
- Source is the external object we discovered. Document is our application’s representation of the content after fetching and parsing the source item. The document is a common format for all sources. SourceItem is one thing discovered inside the source.
- One source item might have more than one documents
- For the MVP we could start with 2 connectors. First Pdf/docx upload. Later website.
- ingestion should be idempotent
- sources should be synchronized
- adding a new source and periodically checking an existing source should reuse essentially the same connector logic
- Store the raw source before processing. In s3 so that if you have a new parser re parse it etc. without hammering the original websites again.
- For MVP structure-aware recursive chunking.
- But chunking algorithm should be easily replaceable
- inspect images once during ingestion using a vision model, turn useful images into textual captions, and index those captions as separate chunks (maybe not for the MVP)
- batch embedding requests when possible for better efficiency 
- A good default for your MVP would be: retrieve perhaps 30–100 candidates from each retriever, fuse them with RRF, then send the best 20–50 fused candidates to the reranker.
- Make reranking configurable true/false. In reranking add a max_chunks_per_document parameter so that not all chunks return from the same document which might be duplicated information. So if this is not a parameter on the hosted service, rerank all RRF top results and then select locally the final 10. 
- Retrieval and answer apis should remain separate. The retrieval system should be useful without forcing users to use our LLM
- Initially one Celery worker consumes everything. sync and parse could be in the same “ingestion” queue for MVP. There is also an embed queue
- Use the transactional outbox pattern in the MVP. Consumers need to be idempotent. 

---

# 30. Additional implementation guidelines extracted from the notes

These are important constraints stated elsewhere in the document and should be treated as project guidance:

- Keep ingestion and query execution as separate operational paths: ingestion is asynchronous; retrieval is synchronous and low-latency.
- Use PostgreSQL + pgvector + PostgreSQL FTS for the MVP rather than introducing a dedicated vector database or search cluster.
- Use an HNSW pgvector index for semantic retrieval.
- PostgreSQL FTS is acceptable for the MVP even though its ranking is not BM25.
- Fuse lexical and vector rankings with RRF rather than directly mixing their raw scores.
- Do not add query rewriting/decomposition or deep/agentic retrieval to the first MVP.
- Persist the raw uploaded file before parsing.
- Persist chunks before enqueueing embedding work.
- Use one DB transaction to persist chunks and the corresponding outbox event.
- Do not keep a database transaction open across remote API calls.
- Make external parser, embedding, reranking and LLM providers replaceable through explicit interfaces.
- Batch embedding requests.
- Preserve normalized document structure and source metadata through chunk creation.
- Old/stale chunks must not remain in the active retrieval index after a source is updated.
- Use `project_id` consistently as the knowledge-base/tenant boundary.
- Avoid complex document-level ACLs in the MVP.
- Log retrieval queries and enough intermediate retrieval information to support debugging and future evaluation.
- Use Recall@K and MRR as initial retrieval-quality metrics.
- Leave room for future `image_caption` chunks, but do not implement image understanding in the first MVP.
- Prefer ordinary HTTP fetching over browser rendering for future website ingestion; use Playwright only as a fallback.
- Treat the current database model as a starting draft, not as a frozen schema.
- Do not implement future team/invite/public-project UI features just because the long-term model supports them.
- Use the Unstructured hosted API for the MVP, but keep parsing behind a replaceable provider abstraction so local Unstructured or another parser can be substituted later.

---

## 31. Current design status / open decisions

The project is ready to move from architecture notes into step-by-step implementation planning.

The main architecture is already decided:

- FastAPI backend
- PostgreSQL + pgvector
- PostgreSQL FTS
- RabbitMQ
- Celery
- S3/MinIO
- PDF/DOCX first
- Unstructured hosted API parsing
- structure-aware chunking
- Voyage embeddings
- RRF
- Voyage reranking
- Groq answer generation
- JWT auth
- transactional outbox
- retrieval evaluation

Important unresolved or implementation-level decisions:

1. Exact user/workspace/team table structure for the simplified MVP while preserving the long-term model.
2. Exact REST resource shapes and status/state model.
3. Exact representation of normalized elements and metadata in PostgreSQL.
4. Exact embedding vector dimension / pgvector column configuration for the chosen Voyage model.
5. Exact RRF constant and retrieval candidate counts.
6. Exact query-log detail retained in production.
7. Exact S3/MinIO object-key convention.
9. Exact deletion/update semantics for stale documents and chunks.

Implementation planning should resolve these one at a time while preserving the architectural boundaries above.

---

## 32. Recommended implementation-planning principle

Plan and implement the MVP as small vertical slices.

A good first end-to-end slice is:

```text
register/login
  -> create project
  -> upload one PDF/DOCX
  -> store raw file
  -> parse
  -> normalize
  -> chunk
  -> embed
  -> index
  -> /retrieve
  -> return grounded chunks
```

Then add:

```text
reranking
  -> /answer
  -> query logging/evaluation
  -> ingestion robustness/outbox refinements
  -> UI polish
  -> website connector
```

The agent should avoid building every subsystem horizontally before one end-to-end retrieval path works.
