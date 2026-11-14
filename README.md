# Loctapus

Loctapus is a platform that brings together knowledge from multiple sources into a unified, 
searchable knowledge base and makes it accessible to applications, AI agents, and users 
through various interfaces, including web chat, APIs, and MCP. 

The project is still under development. Currently, it supports PDF and DOCX uploads as knowledge sources, 
with web chat as the only available interface. Support for additional sources and interfaces is coming soon.

## How the project is developed

- An initial MVP specification
  ([docs/2026-10-06-initial_rag_mvp_agent_project_context.md](docs/2026-10-06-initial_rag_mvp_agent_project_context.md))
  was distilled from a long conversation with GPT-6 Sol. It describes, at a high level, what
  a first working version must do.
- A roadmap ([docs/superpowers/specs/2026-10-06-roadmap.md](docs/superpowers/specs/2026-10-06-roadmap.md))
  breaks that specification into small vertical slices. Each slice spans the whole stack
  (database, API and front end), so it can be tested end to end as soon as it is done.
- All work is done by AI agents in [OpenCode](https://opencode.ai) with models from
  [OpenRouter](https://openrouter.ai), following the
  [obra/superpowers](https://github.com/obra/superpowers) methodology.

## Architecture

### Services

The system runs as 8 Docker Compose services:

| Service                  | Role                                                                 |
| ------------------------ | -------------------------------------------------------------------- |
| `db`                     | PostgreSQL with pgvector: all data, including chunk embeddings       |
| `rabbitmq`               | Message broker for background tasks                                  |
| `garage`                 | S3-compatible storage for the uploaded files                         |
| `one-off-initialization` | Applies database migrations before the API starts, then exits        |
| `api`                    | FastAPI application                                                  |
| `worker`                 | Celery worker that runs the background tasks                         |
| `dispatcher`             | Reads pending tasks from the outbox table and sends them to RabbitMQ |
| `web`                    | Caddy: serves the React app and forwards `/api/` to the API          |

### Ingesting a file (background)

Background tasks use the **transactional outbox pattern**: a task is first saved in an
`outbox` database table in the same transaction as the data it refers to, and the dispatcher
later publishes it to RabbitMQ. This way a task is never lost, and never sent for data that
was not saved.

1. The user uploads a file. The API stores it in Garage and adds an ingestion task to the
   outbox.
2. The dispatcher publishes the task to the ingestion queue.
3. A worker fetches the file, parses it, splits it into chunks and adds an embedding task to
   the outbox.
4. The dispatcher publishes it to the embedding queue.
5. A worker embeds the chunks in batches, stores the embeddings, and marks the file as ready
   once all its chunks are done.

### Asking a question (synchronous)

1. An LLM router decides how to answer:
   - **direct** - use only the chat history,
   - **reuse** - use the history plus previously retrieved chunks,
   - **retrieve** - run a new search.
2. Retrieval embeds the question and searches in two ways: vector search (cosine similarity
   over the chunk embeddings) and full-text search. The two result lists are merged with
   reciprocal rank fusion, and a diverse subset of chunks is selected.
3. The LLM writes the answer from those chunks and cites them.
4. The question and the answer are saved, in order, in the user's conversation.

### Tech stack

- **Backend:** Python, FastAPI, SQLAlchemy, Celery
- **Front end:** React with Vite
- **Database:** PostgreSQL with pgvector
- **Extensibility:** the parser, reranker and LLM providers sit behind generic interfaces, so
  a provider can be swapped without touching the rest of the code. Chunking is a basic
  structure-aware algorithm that can be replaced with a more advanced one.

### Run it locally

You need Docker with Compose 2.24 or newer.

```powershell
copy deploy\.env.example deploy\.env
copy backend\.env.example backend\.env
docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml down            # Data is kept in volumes and persists across runs.
```

- Web UI: http://localhost:8080
- API docs: http://localhost:8000/api/docs

`deploy/.env` holds the service credentials and `backend/.env` the app settings. The template
values are public development credentials: generate fresh ones (for example
`openssl rand -hex 32`) for any public deployment. Do not change `GARAGE_DEFAULT_SECRET_KEY`
after the first start, or Garage will fail to start until its volume is wiped.


### Using a real LLM

By default the system works offline with a stub LLM that returns a fixed sentence. To use
Groq, set `RAG_LLM_PROVIDER=groq` and `RAG_GROQ_API_KEY` in `backend/.env`, then run `up -d`
again. All settings are listed in `backend/app/core/config.py`.

### Live reload

For development, the dev overlay syncs code edits into the running containers and restarts
or hot-reloads them automatically:

```powershell
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.dev.yml up --build --watch
```

After adding a new database migration, apply it with:

```powershell
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.dev.yml up -d --build one-off-initialization
```

Only one stack can run at a time on a machine. Run `down` before starting it from another
checkout or worktree.

## Tests

Tests need Python 3.14, Node.js, and the compose stack running (they use the real Postgres,
RabbitMQ and Garage).

```powershell
python -m venv .venv
.venv\Scripts\pip install -e "backend[dev]"
npm install --prefix web
```

Backend, from `backend/`:

```powershell
..\.venv\Scripts\python -m pytest                   # Full suite.
..\.venv\Scripts\python -m pytest -m "not long"     # Skips tests slower than 5 seconds.
```

Front end, from `web/`: `npm test` (unit), `npm run e2e` (end to end), `npm run lint`.

Before finishing a change, `ruff check .`, `ruff format --check .` and `mypy app tests` must
also pass (see [AGENTS.md](AGENTS.md)).

## Deployment

The demo runs on a single Hetzner VPS. Development and production share the same base compose
file, and production adds a server-specific override
(`deploy/hetzner/docker-compose.server.yml`). Every push to `master` triggers a GitHub Actions
workflow that updates the live app. Keeping all services on one server keeps costs low and the
setup easy to maintain. Setup, secrets and teardown are described in
[deploy/hetzner/README.md](deploy/hetzner/README.md).

## Further reading

- [System overview](docs/2026-10-19-system-overview.md) - detailed description of the current system
- [Roadmap](docs/superpowers/specs/2026-10-06-roadmap.md) - planned slices
- [Backlog](docs/backlog.md) - follow-ups and deferred findings
