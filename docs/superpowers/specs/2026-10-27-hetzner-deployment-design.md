# Hetzner demo deployment - Design

Date: 2026-10-27
Status: Design round complete (2026-10-27); implementation pending.
Source of truth: the 2026-10-27 design conversation, on top of the compose stack as it
stands (`deploy/docker-compose.yml` with its `deploy/.env.example` credentials contract)
and `2026-10-16-docker-compose-full-stack-design.md`. Where those disagree with this
document on deployment topics, this document wins; where it is silent, they govern.

## 1. Context

The system already runs whole under one compose command: `docker compose -f
deploy/docker-compose.yml up -d` builds and starts Postgres (pgvector), RabbitMQ, Garage,
the one-off migration step, the API, the Celery worker, the outbox dispatcher, and the
web tier. Stack credentials interpolate from the gitignored `deploy/.env` (template
`deploy/.env.example`) with `${VAR:?...}` hard-fail guards; the app-level secrets live in
the gitignored `backend/.env` (`RAG_JWT_SECRET`, plus the Groq opt-in). The repository is
public on GitHub (`github.com/dimyG/RAG`, branch `master`).

This round adds a demo deployment: a single cheap Hetzner VPS serving the system on HTTPS,
with CI/CD such that every push to `master` updates the deployment automatically. It is
explicitly not a production platform: one box, no backups, no zero-downtime, throwaway
demo data (section 8 states exactly what survives what).

Server assumptions: Hetzner CX22 (2 vCPU, 4 GB RAM, 40 GB disk; roughly EUR 4-5 per month),
Ubuntu 24.04, root access, the repository cloned to `/root/RAG`, and a DNS A record for
the demo domain pointing at the VPS before the first deploy (Caddy's certificate issuance
needs it).

## 2. Decisions (2026-10-27 design round)

1. **One VPS, compose, build on the server; GitHub Actions deploys over SSH.** Every push
   to `master` (and every manual `workflow_dispatch`) triggers a workflow that renders the
   env files, copies them to the server, and runs `deploy/hetzner/deploy.sh` over SSH:
   `git pull --ff-only` plus `docker compose up -d --build`. No registry, no image tags,
   no second server. A failed build keeps the old version serving (compose builds before
   it recreates), which is the right failure mode for a demo.
2. **All Hetzner-specific code lives in `deploy/hetzner/`**: the compose override,
   `deploy.sh`, `bootstrap.sh`, and the operator runbook (`README.md`). One exception by
   platform necessity: the workflow file must live at `.github/workflows/deploy.yml`
   (GitHub requires that path); it stays thin glue, and every piece of deploy logic lives
   in `deploy/hetzner/`.
3. **The server runs the base compose file plus a small override**
   (`deploy/hetzner/docker-compose.server.yml`), not a duplicated standalone file that
   would drift. The override clears the dev-only published ports, publishes the web tier
   on 80/443, adds restart policies, and mounts the Caddy data volume (section 4).
4. **nginx is replaced by Caddy; one web server serves the SPA, proxies `/api`, and
   manages TLS.** No double web server. One image and one config serve both worlds:
   locally a plain-HTTP site on :8080, on Hetzner an automatic-HTTPS site on the demo
   domain (section 3).
5. **GitHub Actions secrets are the source of truth for the stack credentials.** The
   workflow renders `deploy/.env` and `backend/.env` onto the server on every deploy, so
   the server files stay pure derived state: never hand-edited, re-rendered identically,
   no drift. Secret names carry prefixes (`STACK_*`, `APP_*`, `HETZNER_*`) because GitHub's
   namespace is flat and a future test workflow might want its own `POSTGRES_PASSWORD`
   (section 5). Alternative provisioning models were weighed in the design round and
   rejected: generate-on-server keeps secrets off GitHub but rebuilds need re-pasting the
   Groq key and offers no central source of truth; SOPS-in-repo adds a decrypt key and
   tool discipline for one file of secrets; an external secret manager is team machinery.
   GitHub rendering gives the strongest rebuild story - fresh VPS plus bootstrap plus one
   workflow run equals a fully configured server.
6. **The workflow pins the server's SSH host key** (`HETZNER_KNOWN_HOSTS` secret,
   populated from `ssh-keyscan` output at bootstrap). Trust-on-first-use is not used; a
   host-key mismatch must stop the deploy. After a VPS rebuild the host key legitimately
   changes, and re-populating the secret is part of the documented rebuild procedure.
7. **The workflow uses plain OpenSSH on the runner, not a third-party action.** The
   deploy needs `scp` for the env files and custom `known_hosts` handling anyway, and
   plain ssh/scp keeps the supply chain at zero third-party actions.
8. **`bootstrap.sh` and `deploy.sh` are separate scripts with different lifecycles and
   privileges.** bootstrap runs once per VPS, by hand (installs Docker, creates swap,
   configures the firewall, clones the repo, installs the CI key); deploy runs on every
   commit, automatically, and only ever touches the checkout and Docker. The CI never
   holds system-provisioning powers. `deploy.sh` must never contain `down` or `down -v`
   (section 8).
9. **Data survives every deploy.** All state lives in named volumes; `up -d --build`
   recreates containers, never volumes. The exhaustive list of destructive actions is
   section 8, and the runbook repeats it verbatim.
10. **Stack credential rotation is tied to fresh volumes** (Garage binds its stored layout
    to its secret on an initialized volume; Postgres and RabbitMQ keep the credentials an
    initialized volume was created with). `RAG_JWT_SECRET` and the Groq key rotate freely.
    Rotation rules are a runbook section.
11. **The web tier is verified by an explicit smoke check, not by e2e.** The Playwright
    suite drives the Vite dev server (:5173) against a native uvicorn (:8001) and never
    touches the web container, so the nginx-to-Caddy swap adds its own verification list
    (section 10).

## 3. Web tier: nginx -> Caddy

### 3.1 Caddyfile (`web/Caddyfile`, replaces `web/nginx.conf`)

```caddyfile
{$SITE_ADDRESS}

request_body {
    # max_upload_mb (25) with headroom; the 1 MB default would reject uploads.
    max_size 26MB
}

handle /api/* {
    # No URI rewrite: the backend serves the /api prefix itself.
    reverse_proxy api:8000
}

handle {
    root * /srv
    # SPA history-routing fallback.
    try_files {path} /index.html
    file_server
}
```

`{$SITE_ADDRESS}` is Caddyfile environment substitution, not compose interpolation: the
value arrives as a container env var set by compose, which reads it from `deploy/.env`
(the web service gains `SITE_ADDRESS: ${SITE_ADDRESS:?set in deploy/.env}`). Locally
`SITE_ADDRESS=":8080"`: Caddy serves plain HTTP on 8080 and automatic HTTPS stays off (a
port-only site address never triggers ACME). On Hetzner the rendered `deploy/.env`
carries the demo domain: Caddy binds 80 and 443, obtains a Let's Encrypt certificate
automatically, and redirects HTTP to HTTPS.

Behavior parity with the nginx config it replaces:

| nginx.conf | Caddyfile | Note |
| --- | --- | --- |
| `listen 80` | `{$SITE_ADDRESS}` | HTTP locally, automatic HTTPS on the server |
| `client_max_body_size 26m` | `request_body { max_size 26MB }` | upload headroom |
| `resolver 127.0.0.11` + `set $upstream_api` | `reverse_proxy api:8000` | verification point (a) |
| `location /api/ { proxy_pass }`, no URI rewrite | `handle /api/*` | full URI passthrough |
| `try_files $uri $uri/ /index.html` | `try_files {path} /index.html` | SPA fallback |
| `proxy_set_header X-Forwarded-*` | Caddy sets them by default | uvicorn trusts them (`--forwarded-allow-ips=*`) |

The SPA keeps its baked relative `/api` base URL (the web Dockerfile passes no build
args), so every API call stays same-origin under both HTTP and HTTPS - no CORS headers
anywhere, unchanged.

### 3.2 Dockerfile (`web/Dockerfile`)

The node build stage is unchanged. The final stage becomes `FROM caddy:2-alpine`, copies
`dist/` to `/srv`, and copies `Caddyfile` to `/etc/caddy/Caddyfile`.

### 3.3 Compose changes for local dev (`deploy/docker-compose.yml`)

The `web` service publishes `8080:8080` (Caddy listens on 8080 in-container; today it is
`8080:80`) and gains the `SITE_ADDRESS` environment entry. Local `deploy/.env` copies need
the new line `SITE_ADDRESS=":8080"`; the `${SITE_ADDRESS:?...}` guard fails loudly on old
copies instead of silently booting, matching the file's existing guard philosophy. The
template `deploy/.env.example` documents it, noting that a public deployment carries the
domain instead. The local UI URL stays `http://localhost:8080`.

### 3.4 Implementation verification points

(a) Caddy must re-resolve the `api` container name as CI recreates it (the nginx resolver
comment existed for exactly this). Caddy 2.5+ re-resolves upstream hostnames periodically;
implementation verifies this on the pinned image with an explicit api-recreate smoke
check (section 10) rather than trusting the changelog.
(b) The exact `request_body` and `try_files` syntax is confirmed against the current
`caddy:2` image before merging.

## 4. The server override (`deploy/hetzner/docker-compose.server.yml`)

Run as `docker compose -f deploy/docker-compose.yml -f
deploy/hetzner/docker-compose.server.yml`. Deltas only:

- `ports: !override []` on `db`, `rabbitmq`, `garage`, and `api`: nothing but the web tier
  is reachable from outside the compose network. The `!override` tag needs Compose 2.24+;
  the server installs a current Docker, and the local machine already requires 2.24+ for
  this compose file's `env_file.path.required` syntax.
- `web`: `ports: !override ["80:80", "443:443"]`.
- `restart: unless-stopped` on the seven long-running services (db, rabbitmq, garage,
  api, worker, dispatcher, web) so the stack survives reboots; `one-off-initialization`
  keeps `restart: "no"`.
- A named `caddydata` volume mounted at `/data` on `web`. Load-bearing: without
  persistence across container recreates, every CI deploy would re-request the
  certificate and hit Let's Encrypt's duplicate-certificate rate limit (5 per week).
- No credential entries: they already interpolate from `deploy/.env` in the base file,
  and the CI renders that file (section 5).

Because nothing internal is published, the usual "Docker published ports bypass ufw"
problem does not apply: the firewall and compose agree that only 22, 80, and 443 are
exposed.

## 5. Secrets contract

### 5.1 GitHub Actions secrets

| Group | Secret | Rendered into | Note |
| --- | --- | --- | --- |
| Access | `HETZNER_HOST` | - | server IP |
| Access | `HETZNER_USER` | - | `root` |
| Access | `HETZNER_SSH_KEY` | - | private key of the dedicated CI pair |
| Access | `HETZNER_KNOWN_HOSTS` | - | `ssh-keyscan` output printed by bootstrap |
| Stack | `STACK_POSTGRES_USER` | `deploy/.env` | URL-safe constraint from `.env.example` applies |
| Stack | `STACK_POSTGRES_PASSWORD` | `deploy/.env` | |
| Stack | `STACK_POSTGRES_DB` | `deploy/.env` | |
| Stack | `STACK_RABBITMQ_DEFAULT_USER` | `deploy/.env` | |
| Stack | `STACK_RABBITMQ_DEFAULT_PASS` | `deploy/.env` | |
| Stack | `STACK_GARAGE_RPC_SECRET` | `deploy/.env` | node-to-node RPC auth |
| Stack | `STACK_GARAGE_DEFAULT_ACCESS_KEY` | `deploy/.env` | |
| Stack | `STACK_GARAGE_DEFAULT_SECRET_KEY` | `deploy/.env` | rotation tied to fresh volumes |
| Stack | `STACK_GARAGE_DEFAULT_BUCKET` | `deploy/.env` | |
| Stack | `STACK_GARAGE_ADMIN_TOKEN` | `deploy/.env` | guards the :3903 admin API |
| Stack | `STACK_SITE_ADDRESS` | `deploy/.env` | the demo domain, e.g. `rag.example.com` |
| App | `APP_RAG_JWT_SECRET` | `backend/.env` | token signing |
| App | `APP_RAG_GROQ_API_KEY` | `backend/.env` | optional; unset means the stub provider |

Mapping rule: each `STACK_*` secret renders as the un-prefixed variable (`STACK_X` ->
`X`), each `APP_*` secret as `RAG_X`; the rendered files therefore match the templates
`deploy/.env.example` and `backend/.env.example` variable-for-variable.

### 5.2 The render step (runs on the GitHub runner)

The workflow writes both files from secret values, copies them over SSH, and deletes the
local copies; the runner itself is destroyed when the job ends. No `set -x` anywhere near
this step; GitHub masks secret values in logs automatically.

```bash
printf 'POSTGRES_USER=%s\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=%s\n' \
  "$STACK_POSTGRES_USER" "$STACK_POSTGRES_PASSWORD" "$STACK_POSTGRES_DB" > stack.env
printf 'RABBITMQ_DEFAULT_USER=%s\nRABBITMQ_DEFAULT_PASS=%s\n' \
  "$STACK_RABBITMQ_DEFAULT_USER" "$STACK_RABBITMQ_DEFAULT_PASS" >> stack.env
printf 'GARAGE_RPC_SECRET=%s\nGARAGE_DEFAULT_ACCESS_KEY=%s\nGARAGE_DEFAULT_SECRET_KEY=%s\n' \
  "$STACK_GARAGE_RPC_SECRET" "$STACK_GARAGE_DEFAULT_ACCESS_KEY" "$STACK_GARAGE_DEFAULT_SECRET_KEY" >> stack.env
printf 'GARAGE_DEFAULT_BUCKET=%s\nGARAGE_ADMIN_TOKEN=%s\nSITE_ADDRESS=%s\n' \
  "$STACK_GARAGE_DEFAULT_BUCKET" "$STACK_GARAGE_ADMIN_TOKEN" "$STACK_SITE_ADDRESS" >> stack.env
printf 'RAG_JWT_SECRET=%s\n' "$APP_RAG_JWT_SECRET" > app.env
if [ -n "$APP_RAG_GROQ_API_KEY" ]; then
  printf 'RAG_LLM_PROVIDER=groq\nRAG_GROQ_API_KEY=%s\n' "$APP_RAG_GROQ_API_KEY" >> app.env
fi
scp stack.env "$HETZNER_USER@$HETZNER_HOST:/root/RAG/deploy/.env"
scp app.env "$HETZNER_USER@$HETZNER_HOST:/root/RAG/backend/.env"
rm stack.env app.env
```

The Groq lines are emitted only when the key is set: an empty `RAG_LLM_PROVIDER=` line
would fail pydantic validation, and an unset key means the stub provider keeps the demo
fully offline. Rendering whole files (never patching) keeps the server files pure derived
state - the same `${VAR:?...}` guards as local dev, no hand edits, drift-free.

### 5.3 Transport and rest

Nothing crosses a wire in plaintext. GitHub-to-runner is HTTPS-injected environment
variables; runner-to-server is SSH. At GitHub, secrets are encrypted at rest with logged
access and are readable only by workflows that reference them. On the server, the `.env`
files are plaintext by necessity (compose reads them), protected by 600 root-only
permissions on a single-tenant box - the same model as the local dev copies. `deploy.sh`
enforces the permissions.

### 5.4 Rotation rules

- `STACK_*` credentials: rotate only together with fresh volumes. Garage binds its stored
  layout to `GARAGE_DEFAULT_SECRET_KEY` on an initialized volume; Postgres and RabbitMQ
  keep the credentials an initialized volume was created with. Rotating these on a live
  box is a documented "don't".
- `APP_RAG_JWT_SECRET`: rotates freely; it only invalidates outstanding tokens. Re-run
  the workflow to re-render.
- `APP_RAG_GROQ_API_KEY`: rotates freely. Re-run the workflow to re-render.

## 6. `bootstrap.sh` (`deploy/hetzner/bootstrap.sh`)

Runs once per VPS, by hand, as root, on a fresh Ubuntu 24.04 box. Its commands are
idempotent, but it is never meant to re-run. Steps, in order:

1. `apt update` and `apt upgrade`.
2. Install Docker via the get.docker.com convenience script; enable the service.
3. Create a 2 GB swapfile (build headroom on a 4 GB box).
4. Allow 22, 80, and 443 through ufw; enable ufw.
5. Clone the repository to `/root/RAG` (public repo, no credentials needed).
6. Install the CI deploy public key into `authorized_keys` (passed as a file argument;
   the private key only ever lives in the GitHub secret).
7. Print the `ssh-keyscan` output for the operator to paste into the
   `HETZNER_KNOWN_HOSTS` secret.

Deliberately no secrets in bootstrap: every credential value arrives via the first
workflow run. That is the rebuild story - fresh VPS plus bootstrap plus one workflow run
equals a fully configured server.

## 7. `deploy.sh` and the CI workflow

### 7.1 `deploy.sh` (`deploy/hetzner/deploy.sh`, runs on the server)

```bash
#!/usr/bin/env bash
# Runs on the VPS, invoked by the CI workflow over SSH. Never loses state:
# no down, no down -v, nothing beyond what up recreates.
set -euo pipefail
cd /root/RAG
chmod 600 deploy/.env backend/.env
git pull --ff-only
docker compose -f deploy/docker-compose.yml -f deploy/hetzner/docker-compose.server.yml up -d --build
```

It ships with the code (the workflow executes the checked-out copy), so the deploy logic
can never be out of sync with the tree it deploys.

### 7.2 Workflow (`.github/workflows/deploy.yml`)

- Triggers: push to `master`, plus `workflow_dispatch` (manual re-render and redeploy -
  for example after rotating the Groq key, with no code change).
- `concurrency: group deploy` with `cancel-in-progress: false`: deploys serialize, and a
  compose up is never killed mid-flight.
- Steps: write the SSH key and the pinned known_hosts to temp files from secrets
  (`install -m 600`, no `accept-new`), render the env files (5.2), scp them, then
  `ssh ... 'bash /root/RAG/deploy/hetzner/deploy.sh'`.
- Plain OpenSSH on the runner, no third-party actions (decision 7).

## 8. Data persistence and failure modes

What survives every deploy: everything. All state lives in named volumes - `pgdata`
(users, workspaces, projects, chunks, chat history), `rabbitmqdata`, `garagemeta` and
`garagedata` (uploaded document bytes), `caddydata` (certificates). `up -d --build`
rebuilds images and recreates changed containers only; named volumes are untouched.
Schema changes ride along: a new migration re-runs `one-off-initialization` (its image
changed) and applies forward-only, data-preserving migrations to the existing `pgdata`.

The exhaustive list of destructive actions:

| Action | Volumes |
| --- | --- |
| Every CI deploy (`up -d --build`) | kept |
| `docker compose down` | kept |
| `docker compose down -v` | wiped |
| Deleting the VPS in the Hetzner console | wiped |

Other failure modes and mitigations:

- A broken commit: the build fails, old containers keep serving, the commit shows a red
  X in GitHub.
- ACME rate limits: mitigated by the `caddydata` volume (section 4).
- DNS not yet pointing at the VPS: the first deploy fails loudly at Caddy's certificate
  step; the runbook orders setup as console -> bootstrap -> secrets -> DNS -> first
  deploy.
- Server reboot: `restart: unless-stopped` brings the stack back (section 4).
- Lost Groq key or rotated JWT secret: fixed by a `workflow_dispatch` re-render (5.4).

## 9. Runbook and docs

`deploy/hetzner/README.md` is the operator runbook and carries, as agreed in the design
round:

1. **Bootstrap vs deploy**: the lifecycle distinction - bootstrap once per VPS, by hand
   (what it provisions); deploy on every commit, automatically (what it touches); what
   happens after each; the only case where bootstrap ever runs again (a rebuilt VPS).
2. **Data persistence**: section 8's table verbatim, plus the rule that `deploy.sh` never
   contains `down`/`down -v`.
3. **Secrets transport**: section 5.3's content - encrypted in transit, plaintext at
   rest on the server by design, the rotation rules, and the host-key pinning procedure.
4. **Prerequisites and setup order**: Hetzner console (CX22, Ubuntu 24.04, SSH key),
   `bootstrap.sh`, the GitHub secrets table, the DNS A record, the first workflow
   trigger.
5. **Operations**: SSH tunnels for the now-unpublished RabbitMQ management UI and Garage
   admin, manual redeploys via `workflow_dispatch`, teardown (deleting the VPS deletes
   the data; snapshot first if wanted), and rebuilding the VPS (including re-populating
   `HETZNER_KNOWN_HOSTS`).

The main `README.md` gets a short "Hetzner deployment" section pointing at the runbook.
`docs/2026-10-19-system-overview.md` is updated at implementation end per the house rule.

## 10. Verification

The Playwright e2e suite does not cover the web tier (it drives the Vite dev server on
:5173 against a native uvicorn on :8001), so the swap is verified explicitly:

- `docker compose -f deploy/docker-compose.yml -f
  deploy/hetzner/docker-compose.server.yml config` - the override merges correctly and
  the `${VAR:?}` guards pass.
- With the local stack up (`SITE_ADDRESS=":8080"`): the UI serves at `localhost:8080`; a
  deep-link route returns the SPA; `/api/health` proxies through; an upload works; a
  26 MB-plus body is rejected; and recreating `api` leaves the web tier functional (the
  DNS re-resolution check, verification point 3.4a).
- The pytest and Playwright suites stay green (the swap cannot touch them, but the gates
  run per `AGENTS.md`).
- Server-side: the same smoke over `https://<demo-domain>` after the first deploy.

## 11. Non-goals

No zero-downtime deploys (seconds of recreate during a deploy), no backups or scheduled
snapshots, no image registry, no staging environment, no multi-server story, no ACME
account email (Caddy works without one; backlog candidate), no rotation automation.
Preserving demo data across teardown is the snapshot button in the Hetzner console, not
this system.

## 12. Task dependency sketch (formalized in the implementation plan)

```
A. Caddy swap: web/Caddyfile, web/Dockerfile, compose web service,
   deploy/.env.example gains SITE_ADDRESS        (independent start)
B. Server override: deploy/hetzner/docker-compose.server.yml   (needs A's web shape)
C. deploy.sh                                    (needs B: its compose invocation)
D. bootstrap.sh                                 (independent of A-C)
E. Workflow .github/workflows/deploy.yml        (needs C: what it invokes)
F. Runbook deploy/hetzner/README.md, README pointer, system overview (consumes A-E)
```

A and D are parallelizable; B follows A; C follows B; E follows C; F is last. The
implementation plan assigns one commit per concern per the house git rules.
