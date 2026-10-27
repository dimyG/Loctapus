# Hetzner Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the spec's Hetzner demo deployment: the nginx-to-Caddy web swap, the `deploy/hetzner/` server files (override, `deploy.sh`, `bootstrap.sh`, runbook), and the GitHub Actions SSH deploy pipeline.

**Architecture:** The existing compose stack stays the base; a small server override layers the Hetzner deltas (unpublished internal ports, web on 80/443, restart policies, Caddy data volume). One web image (node build stage -> caddy:2-alpine) serves the SPA, proxies `/api`, and does TLS, with the site address env-driven (`:8080` locally, the demo domain on the server). GitHub Actions is the single deploy path: render `deploy/.env` + `backend/.env` from secrets, scp them, then pull and run `deploy/hetzner/deploy.sh` on the box. `bootstrap.sh` provisions a fresh VPS once, by hand; the CI never has system-provisioning powers.

**Tech Stack:** Docker Compose 2.24+ (`!override`, `env_file.path.required`), Caddy 2 (Caddyfile), GitHub Actions (plain OpenSSH, no third-party actions), bash scripts (LF-pinned by `.gitattributes`), Windows PowerShell for local verification.

**Spec:** `docs/superpowers/specs/2026-10-27-hetzner-deployment-design.md` - the plan argues from the spec; read both. Section numbers below refer to the spec.

## Global Constraints

- All Hetzner-specific code lives in `deploy/hetzner/`; the one exception is `.github/workflows/deploy.yml` (GitHub requires the path) (spec 2).
- Compose 2.24+ is required for `!override` and the `env_file.path.required` syntax (spec 4).
- Web image: `node:24-alpine` build stage unchanged, final stage `caddy:2-alpine`; upload cap is `max_size 26MiB` exactly - never `26MB` (spec 3.1).
- `SITE_ADDRESS` interpolates from `deploy/.env` with the guard `${SITE_ADDRESS:?set in deploy/.env}`; local value `":8080"` (spec 3.3).
- `deploy.sh` never contains `down` or `down -v`; it runs `up -d --build` plus `docker image prune -f` only (spec 7.1, 8).
- GitHub secret names: `HETZNER_HOST`, `HETZNER_USER`, `HETZNER_SSH_KEY`, `HETZNER_KNOWN_HOSTS`; `STACK_*` renders un-prefixed into `deploy/.env` (11 secrets); `APP_RAG_JWT_SECRET` renders with the `APP_` prefix stripped into `backend/.env`; `APP_RAG_GROQ_API_KEY` optional, rendered only when non-empty; `RAG_ENVIRONMENT=production` is a fixed render line reaching the api container only (spec 5.1, 5.2, decision 12).
- The override uses no YAML anchors (anchors do not carry across files); `restart: unless-stopped` on the seven long-running services; `one-off-initialization` keeps `restart: "no"` (spec 4).
- `.gitattributes` pins every text file to LF; every new file, especially the shell scripts, must verify as LF (`git ls-files --eol`) or it breaks on Linux.
- Every `ssh`/`scp` call in the workflow carries `-i key -o UserKnownHostsFile=known_hosts -o StrictHostKeyChecking=yes`; no `accept-new` (spec 5.2, 7.2).
- House gates per `AGENTS.md`: `ruff check .`, `ruff format --check .`, `mypy app tests`, `pytest` (backend scope; run from `backend/`), plus web `lint`/`format:check`/`test`/`e2e` at the end. Comments start with a capital letter and end with a dot; no em dashes anywhere.
- Git: one concern per commit, no co-author lines, branch `hetzner-deployment` (never a detached HEAD).
- The compose system is machine-global: before bringing the stack up from this worktree, `down` it from the main checkout (`D:\Projects\RAG`) per the README.

## Review Focus

The five input classes or failure modes most likely to bite, each pinned to the task whose steps exercise it:

1. **An upload just under the backend's 25 MiB limit (26,214,400 bytes) must reach the backend** and get its 422 copy, and one over 26 MiB must stop at Caddy with 413 - a `26MB` (decimal) typo silently 413s legal uploads. Test: Task 1's upload smoke with exact sizes 26,738,688 (25.5 MB -> 422) and 28,311,552 (27 MB -> 413).
2. **Bare `/api` (no trailing slash) must fall through to the SPA**, exactly as nginx did (open backlog watch item). Test: Task 1's smoke, `curl http://localhost:8080/api` returns the SPA's `index.html`.
3. **A deep-link SPA route on reload must return the SPA**, not 404 (`try_files` fallback parity). Test: Task 1's smoke on `/projects/<uuid>`.
4. **The api container recreated while web keeps running must self-heal** - Caddy re-resolves per connection dial; at most one transient 502. Test: Task 1's `--force-recreate api` step.
5. **An empty Groq key must render no provider lines** - an empty `RAG_LLM_PROVIDER=` line crashes the api container at boot (pydantic `Literal` guard). Test: Task 5's local render dry-run, empty key then set key.

Not locally testable, covered by construction instead: a wrong host-key pin stops the deploy (pinned `StrictHostKeyChecking=yes` in the workflow; rebuild procedure in the runbook, Task 6).

## Task DAG

```
Task 0 (baseline) -> Task 1 (Caddy swap) -> Task 2 (override) -> Task 3 (deploy.sh) -> Task 5 (workflow) -> Task 6 (runbook) -> Task 8 (gates, freeze, finish)
                          |                                                                                            ^
Task 4 (bootstrap.sh) --- +------------------------------------------------------------------------------------------+
                          +-> Task 7 (doc-rot) -------------------------------------------------------------------------+
```

- `Task 4` is independent of Tasks 1-3 and 5; run it in parallel with the 1 -> 2 -> 3 -> 5 chain.
- `Task 7` needs only Task 1's Caddy facts; it can run in parallel with Tasks 2-5.
- `Task 6` consumes every other task's files. `Task 8` is last.

### Task 0: Worktree environment and baseline

**Files:** none tracked (all changes are gitignored or untracked local copies).

**Interfaces:**
- Consumes: the worktree at `C:\Users\dimgeo\.local\share\opencode\worktree\7d50fe\hetzner-deployment`, branch `hetzner-deployment`.
- Produces: a `.venv` with the backend dev deps, `web/node_modules`, local `deploy/.env` and `backend/.env` copies, the compose stack running from this worktree, and a green pytest baseline. Every later task's verification commands assume this.

- [ ] **Step 1: Create the venv and install backend dev deps**

Run from the worktree root (Python 3.14, per the README):

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e "backend[dev]"
```

- [ ] **Step 2: Install the web toolchain**

```powershell
npm install --prefix web
```

- [ ] **Step 3: Create the local env file copies the compose guards require**

```powershell
Copy-Item deploy\.env.example deploy\.env
Copy-Item backend\.env.example backend\.env
```

Both copies are gitignored. Open `backend\.env` and confirm the `RAG_JWT_SECRET` line exists with any non-empty local value (dev mode accepts anything; the file itself is required by the compose `api` service).

- [ ] **Step 4: Stop any stack running from the main checkout**

The system is machine-global (README). From `D:\Projects\RAG`:

```powershell
docker compose -f deploy/docker-compose.yml down
```

- [ ] **Step 5: Bring the stack up from this worktree and verify health**

From the worktree root:

```powershell
docker compose -f deploy/docker-compose.yml up -d --build
```

Expected: all eight services reach healthy/completed; `docker compose -f deploy/docker-compose.yml ps` shows `web` and `api` healthy (this baseline still runs the nginx web image - Task 1 swaps it).

- [ ] **Step 6: Run the pytest baseline**

```powershell
cd backend
..\.venv\Scripts\python -m pytest
```

Expected: all tests pass. Any failure here is a pre-existing environment problem - stop and report before touching anything.

- [ ] **Step 7: No commit**

Nothing tracked changed; the baseline is the deliverable.

### Task 1: Caddy web tier swap

**Files:**
- Create: `web/Caddyfile`
- Modify: `web/Dockerfile`
- Delete: `web/nginx.conf`
- Modify: `deploy/docker-compose.yml` (web service only)
- Modify: `deploy/.env.example`
- Local (untracked): `deploy/.env`

**Interfaces:**
- Consumes: Task 0's running stack and local `deploy/.env`.
- Produces: `rag-web` image with Caddy serving `/srv`, proxying `/api/*` to `api:8000, and a web service exposing `SITE_ADDRESS` and listening on 8080 in-container (Task 2's override publishes 80/443 instead and mounts `/data`).

- [ ] **Step 1: Write `web/Caddyfile`**

Copy verbatim from spec section 3.1 (the `{$SITE_ADDRESS}` site, `request_body { max_size 26MiB }`, the `/api/*` reverse-proxy handle, and the SPA `try_files` handle).

- [ ] **Step 2: Rewrite `web/Dockerfile`**

Keep the node build stage exactly as is; replace the nginx final stage with:

```dockerfile
FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
```

- [ ] **Step 3: Update the web service in `deploy/docker-compose.yml`**

```yaml
  web:
    build: ../web
    image: rag-web
    # Drives Caddy: ":8080" locally (plain HTTP, no ACME), the demo domain on
    # Hetzner (automatic HTTPS on 80/443).
    environment:
      SITE_ADDRESS: ${SITE_ADDRESS:?set in deploy/.env}
    ports:
      - "8080:8080"
    depends_on:
      api:
        condition: service_healthy
```

- [ ] **Step 4: Add `SITE_ADDRESS` to `deploy/.env.example`**

Documented with a comment: the local default `SITE_ADDRESS=":8080"`; a public deployment carries the demo domain instead (it arrives via the CI render).

- [ ] **Step 5: Remove the old nginx config**

```powershell
git rm web/nginx.conf
```

- [ ] **Step 6: Add the line to the local `deploy/.env` (untracked copy)**

`SITE_ADDRESS=":8080"`

- [ ] **Step 7: Verify the compose merge and guards**

```powershell
docker compose -f deploy/docker-compose.yml config
```

Expected: no interpolation error; the `web` service shows `8080:8080` and `SITE_ADDRESS: :8080`.

- [ ] **Step 8: Rebuild and restart the stack**

```powershell
docker compose -f deploy/docker-compose.yml up -d --build
```

Expected: `rag-web` rebuilds with the caddy stage; the stack comes up healthy.

- [ ] **Step 9: Validate the Caddyfile inside the running web container**

```powershell
docker compose -f deploy/docker-compose.yml exec web caddy validate --config /etc/caddy/Caddyfile
```

Expected: `Valid configuration` (this is spec 3.4b - the exact `request_body`/`try_files` syntax proven against the pinned image). Note: validate inside the container so `{$SITE_ADDRESS}` is substituted.

- [ ] **Step 10: Serving smoke (PowerShell)**

```powershell
curl.exe -fsS http://localhost:8080/                     # Expected: the SPA's index.html (200)
curl.exe -fsS http://localhost:8080/projects/00000000-0000-0000-0000-000000000000   # deep link -> index.html
curl.exe -fsS http://localhost:8080/api                  # bare /api -> index.html (parity with the nginx backlog item)
curl.exe -fsS http://localhost:8080/api/health            # Expected: {"status":"ok"}
```

- [ ] **Step 11: Upload-boundary smoke (Review Focus 1)**

Create zero-filled PDFs of the exact boundary sizes, register a smoke user, and upload through the proxy:

```powershell
fsutil file createnew "$env:TEMP\upload_25_5mb.pdf" 26738688   # 25.5 MB - over the backend's 25 MiB, under Caddy's 26 MiB
fsutil file createnew "$env:TEMP\upload_27mb.pdf" 28311552     # 27 MB - over Caddy's 26MiB cap
fsutil file createnew "$env:TEMP\upload_tiny.pdf" 1024         # a legal upload

$reg = Invoke-RestMethod -Method Post -Uri http://localhost:8080/api/auth/register `
  -ContentType 'application/json' -Body '{"email":"smoke@example.com","password":"password123"}'
$proj = Invoke-RestMethod -Method Post -Uri http://localhost:8080/api/projects `
  -Headers @{Authorization="Bearer $($reg.access_token)"} `
  -ContentType 'application/json' -Body ('{"name":"smoke","team_id":"' + $reg.team_id + '"}')

curl.exe -sS -o NUL -w "%{http_code}" -H "Authorization: Bearer $($reg.access_token)" `
  -F "file=@$env:TEMP\upload_tiny.pdf" "http://localhost:8080/api/projects/$($proj.id)/uploads"      # Expected: 201
curl.exe -sS -o NUL -w "%{http_code}" -H "Authorization: Bearer $($reg.access_token)" `
  -F "file=@$env:TEMP\upload_25_5mb.pdf" "http://localhost:8080/api/projects/$($proj.id)/uploads"    # Expected: 422 (backend's refusal)
curl.exe -sS -o NUL -w "%{http_code}" -H "Authorization: Bearer $($reg.access_token)" `
  -F "file=@$env:TEMP\upload_27mb.pdf" "http://localhost:8080/api/projects/$($proj.id)/uploads"     # Expected: 413 (Caddy's refusal)
```

- [ ] **Step 12: api-recreate re-resolution smoke (Review Focus 4)**

```powershell
docker compose -f deploy/docker-compose.yml up -d --force-recreate api
Start-Sleep -Seconds 10
curl.exe -fsS http://localhost:8080/api/health
```

Expected: `{"status":"ok"}`. One transient 502 immediately after the recreate is acceptable (stale keepalive, spec 3.4a); retry after a few seconds - a persistent 502 fails this task.

- [ ] **Step 13: Run the backend gate**

```powershell
cd backend
..\.venv\Scripts\python -m pytest
```

Expected: pass (no backend code changed; the stack is up).

- [ ] **Step 14: Commit**

```powershell
git add web/Caddyfile web/Dockerfile deploy/docker-compose.yml deploy/.env.example
git commit -m "build(web): swap nginx for Caddy"
```

(`web/nginx.conf` removal is already staged from Step 5.)

### Task 2: Server compose override

**Files:**
- Create: `deploy/hetzner/docker-compose.server.yml`

**Interfaces:**
- Consumes: Task 1's web shape (`SITE_ADDRESS` env entry, Caddy `/data` directory in the image).
- Produces: the override file Task 3's `deploy.sh` invokes and Task 6's runbook documents; the `caddydata` volume name.

- [ ] **Step 1: Write `deploy/hetzner/docker-compose.server.yml`**

Exactly this content (spelled out per service - no anchors, spec section 4):

```yaml
# Server delta over deploy/docker-compose.yml for the Hetzner demo: only the
# web tier is published (80/443), services survive reboots, and Caddy's
# certificates survive container recreates. Run with:
#   docker compose -f deploy/docker-compose.yml -f deploy/hetzner/docker-compose.server.yml
# YAML anchors do not carry across files, so every service spells out its keys.

services:
  db:
    ports: !override []
    restart: unless-stopped

  rabbitmq:
    ports: !override []
    restart: unless-stopped

  garage:
    ports: !override []
    restart: unless-stopped

  api:
    ports: !override []
    restart: unless-stopped

  worker:
    restart: unless-stopped

  dispatcher:
    restart: unless-stopped

  web:
    ports: !override ["80:80", "443:443"]
    restart: unless-stopped
    volumes:
      - caddydata:/data

volumes:
  caddydata:
```

- [ ] **Step 2: Render the merged config**

```powershell
docker compose -f deploy/docker-compose.yml -f deploy/hetzner/docker-compose.server.yml config | Out-File -Encoding utf8 $env:TEMP\merged.yml
```

Expected: renders with no interpolation error (Task 0's local `deploy/.env` feeds the guards).

- [ ] **Step 3: Assert the server posture on the merged config**

```powershell
(Select-String -Path $env:TEMP\merged.yml -Pattern 'published:').Count                 # Expected: 2 (80 and 443, both web)
(Select-String -Path $env:TEMP\merged.yml -Pattern 'restart: unless-stopped').Count    # Expected: 7
(Select-String -Path $env:TEMP\merged.yml -Pattern 'caddydata').Count                 # Expected: 2 (web mount + volumes)
(Select-String -Path $env:TEMP\merged.yml -Pattern 'restart: "no"').Count              # Expected: 1 (one-off-initialization)
```

The `published:` count of 2 also proves the internal ports (5432, 5672, 15672, 3900, 3903, 8000) are gone from the server posture.

- [ ] **Step 4: Commit**

```powershell
git add deploy/hetzner/docker-compose.server.yml
git commit -m "feat(deploy): add the Hetzner server compose override"
```

### Task 3: deploy script

**Files:**
- Create: `deploy/hetzner/deploy.sh`

**Interfaces:**
- Consumes: Task 2's override path and the base compose file.
- Produces: the exact deploy entry point Task 5's workflow invokes over SSH and Task 6's runbook documents.

- [ ] **Step 1: Write `deploy/hetzner/deploy.sh`**

Copy verbatim from spec section 7.1 (shebang, the two header comments, `set -euo pipefail`, `cd /root/RAG`, `chmod 600 deploy/.env backend/.env`, the two-file `docker compose ... up -d --build`, and `docker image prune -f`).

- [ ] **Step 2: Verify LF line endings before anything else**

A CRLF copy breaks bash on Linux. After staging:

```powershell
git add deploy/hetzner/deploy.sh
git ls-files --eol deploy/hetzner/deploy.sh
```

Expected: `i/lf` and `w/lf`. If `w/crlf` appears, rewrite the file with LF (`(Get-Content deploy\hetzner\deploy.sh -Raw) -replace "`r`n","`n" | Set-Content -NoNewline deploy\hetzner\deploy.sh`) and re-add.

- [ ] **Step 3: Syntax check**

```powershell
bash -n deploy/hetzner/deploy.sh
```

Expected: no output, exit 0 (Git for Windows bash is on PATH; `bash -n` also fails on CRLF contamination).

- [ ] **Step 4: Assert the never-loses-state invariant**

```powershell
Select-String -Path deploy\hetzner\deploy.sh -Pattern 'docker compose'
```

Expected: exactly one match, containing `up -d --build` and no `down` (spec decision 8).

- [ ] **Step 5: Commit**

```powershell
git commit -m "feat(deploy): add the server deploy script"
```

(Already staged in Step 2; keep the commit to this one file.)

### Task 4: VPS bootstrap script (parallel with Tasks 1-3)

**Files:**
- Create: `deploy/hetzner/bootstrap.sh`

**Interfaces:**
- Consumes: nothing from earlier tasks (independent).
- Produces: the bootstrap entry point Task 6's runbook pins for invocation, including the printed host-key pin that goes into `HETZNER_KNOWN_HOSTS`, and the contract that the repo lives at `/root/RAG` with pre-created 600-mode `deploy/.env` and `backend/.env`.

- [ ] **Step 1: Write `deploy/hetzner/bootstrap.sh`**

Exactly this content:

```bash
#!/usr/bin/env bash
# One-shot provisioning of a fresh Hetzner VPS for the RAG demo: Docker, swap,
# firewall, the repo clone, the CI deploy key, and the host-key pin. Run once,
# as root. No secret values live here - they all arrive via the first deploy.
set -euo pipefail

public_key_file="${1:?usage: bootstrap.sh <ci-deploy-public-key-file>}"

apt-get update
apt-get upgrade -y
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# Build headroom on a 4 GB box.
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Firewall: SSH plus the two published web ports.
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# The application tree (public repository, no credentials needed).
git clone https://github.com/dimyG/RAG.git /root/RAG

# The CI deploy key: its private half only ever lives in GitHub secrets.
mkdir -p /root/.ssh
chmod 700 /root/.ssh
cat "$public_key_file" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

# Pre-create the env files the CI renders into, so the first scp writes into
# 600-mode files instead of creating world-readable ones.
install -m 600 /dev/null /root/RAG/deploy/.env
install -m 600 /dev/null /root/RAG/backend/.env

# The host-key pin: keyed by the public IPv4 the CI connects to.
public_ip="$(curl -fsS http://169.254.169.254/hetzner/v1/metadata/public-ipv4)"
echo "Paste the following line into the HETZNER_KNOWN_HOSTS secret,"
echo "and set HETZNER_HOST to the same address:"
ssh-keyscan -t ed25519 "$public_ip"
```

- [ ] **Step 2: Verify LF line endings**

```powershell
git add deploy/hetzner/bootstrap.sh
git ls-files --eol deploy/hetzner/bootstrap.sh
```

Expected: `i/lf` and `w/lf` (same fix as Task 3 Step 2 if not).

- [ ] **Step 3: Syntax check**

```powershell
bash -n deploy/hetzner/bootstrap.sh
```

Expected: no output, exit 0.

- [ ] **Step 4: Assert the no-secrets and keyscan contracts**

```powershell
Select-String -Path deploy\hetzner\bootstrap.sh -Pattern '169.254.169.254'   # Expected: 1 (Hetzner metadata service)
Select-String -Path deploy\hetzner\bootstrap.sh -Pattern 'ssh-keyscan'        # Expected: 1
Select-String -Path deploy\hetzner\bootstrap.sh -Pattern 'PASSWORD=|SECRET_KEY=|JWT'  # Expected: 0 (no credential values)
```

- [ ] **Step 5: Commit**

```powershell
git commit -m "feat(deploy): add the VPS bootstrap script"
```

### Task 5: CI deploy workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: Task 3's script path (`deploy/hetzner/deploy.sh` invoked after the workflow's own pull), Task 4's `/root/RAG` and 600-mode file contracts, and the 17 secret names from spec 5.1.
- Produces: the workflow Task 6's runbook documents (triggers, `workflow_dispatch` for secret re-renders, serialized concurrency).

- [ ] **Step 1: Write `.github/workflows/deploy.yml`**

Exactly this content (the render block is spec 5.2 verbatim; the rest assembles spec 7.2):

```yaml
name: Deploy to Hetzner

# Every push to master updates the demo server; workflow_dispatch re-renders
# the env files and redeploys without a code change (first deploy, rotation).
on:
  push:
    branches: [master]
  workflow_dispatch:

# Deploys serialize: a compose up is never killed mid-flight. At most one run
# waits; a newer pending run replaces it, which is harmless because the pull
# always fetches the branch tip.
concurrency:
  group: deploy
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Render env files and deploy over SSH
        env:
          HETZNER_HOST: ${{ secrets.HETZNER_HOST }}
          HETZNER_USER: ${{ secrets.HETZNER_USER }}
          HETZNER_SSH_KEY: ${{ secrets.HETZNER_SSH_KEY }}
          HETZNER_KNOWN_HOSTS: ${{ secrets.HETZNER_KNOWN_HOSTS }}
          STACK_POSTGRES_USER: ${{ secrets.STACK_POSTGRES_USER }}
          STACK_POSTGRES_PASSWORD: ${{ secrets.STACK_POSTGRES_PASSWORD }}
          STACK_POSTGRES_DB: ${{ secrets.STACK_POSTGRES_DB }}
          STACK_RABBITMQ_DEFAULT_USER: ${{ secrets.STACK_RABBITMQ_DEFAULT_USER }}
          STACK_RABBITMQ_DEFAULT_PASS: ${{ secrets.STACK_RABBITMQ_DEFAULT_PASS }}
          STACK_GARAGE_RPC_SECRET: ${{ secrets.STACK_GARAGE_RPC_SECRET }}
          STACK_GARAGE_DEFAULT_ACCESS_KEY: ${{ secrets.STACK_GARAGE_DEFAULT_ACCESS_KEY }}
          STACK_GARAGE_DEFAULT_SECRET_KEY: ${{ secrets.STACK_GARAGE_DEFAULT_SECRET_KEY }}
          STACK_GARAGE_DEFAULT_BUCKET: ${{ secrets.STACK_GARAGE_DEFAULT_BUCKET }}
          STACK_GARAGE_ADMIN_TOKEN: ${{ secrets.STACK_GARAGE_ADMIN_TOKEN }}
          STACK_SITE_ADDRESS: ${{ secrets.STACK_SITE_ADDRESS }}
          APP_RAG_JWT_SECRET: ${{ secrets.APP_RAG_JWT_SECRET }}
          APP_RAG_GROQ_API_KEY: ${{ secrets.APP_RAG_GROQ_API_KEY }}
        run: |
          set -euo pipefail
          # Key material: the pinned known_hosts is what enforces the pin.
          install -m 600 /dev/null key
          printf '%s\n' "$HETZNER_SSH_KEY" > key
          install -m 600 /dev/null known_hosts
          printf '%s\n' "$HETZNER_KNOWN_HOSTS" > known_hosts
          ssh_opts=(-i key -o UserKnownHostsFile=known_hosts -o StrictHostKeyChecking=yes)
          # Render deploy/.env: STACK_* secrets, un-prefixed.
          printf 'POSTGRES_USER=%s\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=%s\n' \
            "$STACK_POSTGRES_USER" "$STACK_POSTGRES_PASSWORD" "$STACK_POSTGRES_DB" > stack.env
          printf 'RABBITMQ_DEFAULT_USER=%s\nRABBITMQ_DEFAULT_PASS=%s\n' \
            "$STACK_RABBITMQ_DEFAULT_USER" "$STACK_RABBITMQ_DEFAULT_PASS" >> stack.env
          printf 'GARAGE_RPC_SECRET=%s\nGARAGE_DEFAULT_ACCESS_KEY=%s\nGARAGE_DEFAULT_SECRET_KEY=%s\n' \
            "$STACK_GARAGE_RPC_SECRET" "$STACK_GARAGE_DEFAULT_ACCESS_KEY" "$STACK_GARAGE_DEFAULT_SECRET_KEY" >> stack.env
          printf 'GARAGE_DEFAULT_BUCKET=%s\nGARAGE_ADMIN_TOKEN=%s\nSITE_ADDRESS=%s\n' \
            "$STACK_GARAGE_DEFAULT_BUCKET" "$STACK_GARAGE_ADMIN_TOKEN" "$STACK_SITE_ADDRESS" >> stack.env
          # Render backend/.env: APP_* stripped, production mode fixed, Groq
          # lines only when the key is set (an empty provider line fails boot).
          printf 'RAG_JWT_SECRET=%s\nRAG_ENVIRONMENT=production\n' "$APP_RAG_JWT_SECRET" > app.env
          if [ -n "$APP_RAG_GROQ_API_KEY" ]; then
            printf 'RAG_LLM_PROVIDER=groq\nRAG_GROQ_API_KEY=%s\n' "$APP_RAG_GROQ_API_KEY" >> app.env
          fi
          scp "${ssh_opts[@]}" stack.env "$HETZNER_USER@$HETZNER_HOST:/root/RAG/deploy/.env"
          scp "${ssh_opts[@]}" app.env "$HETZNER_USER@$HETZNER_HOST:/root/RAG/backend/.env"
          ssh "${ssh_opts[@]}" "$HETZNER_USER@$HETZNER_HOST" \
            'cd /root/RAG && git pull --ff-only && bash deploy/hetzner/deploy.sh'
          rm -f key known_hosts stack.env app.env
```

- [ ] **Step 2: Verify LF line endings**

```powershell
git add .github/workflows/deploy.yml
git ls-files --eol .github/workflows/deploy.yml
```

Expected: `i/lf` and `w/lf`.

- [ ] **Step 3: Parse the YAML**

```powershell
D:\Projects\RAG\.venv\Scripts\python.exe -c "import yaml; yaml.safe_load(open(r'.github/workflows/deploy.yml', encoding='utf-8')); print('yaml ok')"
```

Expected: `yaml ok` (pyyaml is present in the main checkout's venv; verified 2026-10-27).

- [ ] **Step 4: Render dry-run with an empty Groq key (Review Focus 5)**

Extract the render block into a throwaway script and run it with dummy values, twice. Bash inherits the PowerShell environment, so the dummy values are plain `$env:` assignments:

```powershell
@'
set -euo pipefail
printf 'POSTGRES_USER=%s\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=%s\n' "$STACK_POSTGRES_USER" "$STACK_POSTGRES_PASSWORD" "$STACK_POSTGRES_DB" > stack.env
printf 'RABBITMQ_DEFAULT_USER=%s\nRABBITMQ_DEFAULT_PASS=%s\n' "$STACK_RABBITMQ_DEFAULT_USER" "$STACK_RABBITMQ_DEFAULT_PASS" >> stack.env
printf 'GARAGE_RPC_SECRET=%s\nGARAGE_DEFAULT_ACCESS_KEY=%s\nGARAGE_DEFAULT_SECRET_KEY=%s\n' "$STACK_GARAGE_RPC_SECRET" "$STACK_GARAGE_DEFAULT_ACCESS_KEY" "$STACK_GARAGE_DEFAULT_SECRET_KEY" >> stack.env
printf 'GARAGE_DEFAULT_BUCKET=%s\nGARAGE_ADMIN_TOKEN=%s\nSITE_ADDRESS=%s\n' "$STACK_GARAGE_DEFAULT_BUCKET" "$STACK_GARAGE_ADMIN_TOKEN" "$STACK_SITE_ADDRESS" >> stack.env
printf 'RAG_JWT_SECRET=%s\nRAG_ENVIRONMENT=production\n' "$APP_RAG_JWT_SECRET" > app.env
if [ -n "$APP_RAG_GROQ_API_KEY" ]; then
  printf 'RAG_LLM_PROVIDER=groq\nRAG_GROQ_API_KEY=%s\n' "$APP_RAG_GROQ_API_KEY" >> app.env
fi
'@ | Set-Content -Encoding ascii $env:TEMP\render_test.sh

# Dummy values, empty Groq key first.
$env:STACK_POSTGRES_USER='u'; $env:STACK_POSTGRES_PASSWORD='p'; $env:STACK_POSTGRES_DB='d'
$env:STACK_RABBITMQ_DEFAULT_USER='ru'; $env:STACK_RABBITMQ_DEFAULT_PASS='rp'
$env:STACK_GARAGE_RPC_SECRET='rs'; $env:STACK_GARAGE_DEFAULT_ACCESS_KEY='ak'
$env:STACK_GARAGE_DEFAULT_SECRET_KEY='sk'; $env:STACK_GARAGE_DEFAULT_BUCKET='b'
$env:STACK_GARAGE_ADMIN_TOKEN='at'; $env:STACK_SITE_ADDRESS='demo.example.com'
$env:APP_RAG_JWT_SECRET='jjj'; $env:APP_RAG_GROQ_API_KEY=''
Push-Location $env:TEMP
bash render_test.sh
Get-Content stack.env   # Expected: 11 lines, dummy values in the order above
Get-Content app.env     # Expected: exactly 2 lines - RAG_JWT_SECRET=jjj, RAG_ENVIRONMENT=production

# Set the Groq key and re-render - app.env must gain exactly the two groq lines.
$env:APP_RAG_GROQ_API_KEY='gk123'
bash render_test.sh
Get-Content app.env     # Expected: 4 lines, ending in RAG_LLM_PROVIDER=groq and RAG_GROQ_API_KEY=gk123
Pop-Location
Remove-Item $env:TEMP\render_test.sh, $env:TEMP\stack.env, $env:TEMP\app.env
```

The authoritative end-to-end validation is the first live workflow run (Task 6's runbook ordering); this dry-run pins the render logic.

- [ ] **Step 5: Commit**

```powershell
git commit -m "ci: add the Hetzner SSH deploy workflow"
```

(Staged in Step 2; one concern, one file.)

### Task 6: Operator runbook

**Files:**
- Create: `deploy/hetzner/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: every earlier task's files and contracts; spec sections 8, 9, 5.1, 5.3, 5.4; Task 4's bootstrap invocation needs the raw-GitHub fetch recipe (the repo is not cloned yet when bootstrap runs).
- Produces: the operator runbook; the main README gains a pointer section.

- [ ] **Step 1: Write `deploy/hetzner/README.md` with these sections, in order**

1. **Bootstrap vs deploy** - the lifecycle distinction (spec decision 8): bootstrap once per VPS, by hand (Docker, swap, firewall, clone, CI key, host-key pin); deploy on every push to `master`, automatically (render, scp, pull, `up -d --build`); bootstrap ever again only on a rebuilt VPS. Include the invocation recipe:
   ```
   ssh-keygen -t ed25519 -f ci_deploy -N ""   # local; the private half becomes HETZNER_SSH_KEY
   scp ci_deploy.pub root@<server-ip>:/root/ci_deploy.pub
   ssh root@<server-ip> 'curl -fsSL https://raw.githubusercontent.com/dimyG/RAG/master/deploy/hetzner/bootstrap.sh | bash -s /root/ci_deploy.pub'
   ```
2. **Prerequisites and setup order** - Hetzner console (CX23, Ubuntu 24.04, SSH key; the availability caveat with CAX11/CPX22 fallbacks), DNS (A record pointing at the VPS; any AAAA record points at the VPS or is absent), the GitHub secrets table (copy spec 5.1's table verbatim), then the first trigger (a push, or `workflow_dispatch`).
3. **Data persistence** - spec section 8's destructive-actions table verbatim, what survives every deploy, the migration note, and the rule that `deploy.sh` never contains `down`/`down -v`.
4. **Secrets transport and rotation** - spec 5.3 (encrypted in transit: HTTPS then SSH; plaintext at rest on the server by design, 600 root-only) and 5.4's rotation rules (stack credentials only with fresh volumes; JWT and Groq keys free; re-run the workflow after rotating), plus the host-key pin procedure (paste bootstrap's `ssh-keyscan` output into `HETZNER_KNOWN_HOSTS`; `HETZNER_HOST` is the same IP; re-populate after a VPS rebuild).
5. **Operations** - redeploys via `workflow_dispatch`; the pending-run rule (serialized, one waiting run, newer replaces older - harmless since the pull fetches the tip); admin UIs behind SSH with a loopback-only socat forward (the ports are unpublished on the server):
   ```
   ssh root@<server-ip>
   docker run -d --rm --name admin-ui --network rag_default -p 127.0.0.1:15672:15672 alpine/socat tcp-listen:15672,fork,reuseaddr tcp:rabbitmq:15672
   # then, from the local machine: ssh -N -L 15672:localhost:15672 root@<server-ip>
   # browse http://localhost:15672 ; stop the forward with: docker rm -f admin-ui
   ```
   (same pattern with `3903:3903` and `tcp:garage:3903` for the Garage admin); teardown (deleting the VPS deletes all data - snapshot first if wanted); rebuilding the VPS (bootstrap again, re-populate `HETZNER_KNOWN_HOSTS`, fresh volumes accept the same rendered secrets); the optional `command="..."` `authorized_keys` hardening for the CI key (decision 8).
6. A closing line pointing at the spec for the design rationale.

- [ ] **Step 2: Add the pointer section to `README.md`**

A short `## Hetzner deployment` section after the local runbook sections: one sentence (pushes to `master` auto-deploy the demo server via GitHub Actions; bootstrap, secrets, rotation, and teardown live in the runbook) plus the `deploy/hetzner/README.md` link.

- [ ] **Step 3: Cross-check every reference**

```powershell
Test-Path deploy\hetzner\README.md, deploy\hetzner\bootstrap.sh, deploy\hetzner\deploy.sh, deploy\hetzner\docker-compose.server.yml, .github\workflows\deploy.yml   # Expected: all True
(Select-String -Path .github\workflows\deploy.yml -Pattern 'secrets\.').Count   # Expected: 17 - every name also appears in the runbook's secrets table
```

- [ ] **Step 4: Commit**

```powershell
git add deploy/hetzner/README.md README.md
git commit -m "docs: add the Hetzner operator runbook"
```

### Task 7: Doc-rot re-anchor and backlog (parallel with Tasks 2-5; needs Task 1)

**Files:**
- Modify: `docs/2026-10-19-system-overview.md`
- Modify: `backend/app/core/config.py` (one comment)
- Modify: `docs/backlog.md`

**Interfaces:**
- Consumes: Task 1's Caddy behaviors.
- Produces: docs that describe Caddy instead of nginx; a timestamped backlog section for the follow-ups.

- [ ] **Step 1: Re-anchor the nginx references in `docs/2026-10-19-system-overview.md`**

Every nginx mention becomes its Caddy equivalent: the served-by line and architecture node (nginx -> Caddy, TLS added), the same-origin note (Caddy proxies `/api`), and the 60s `proxy_read_timeout` budget claim - under Caddy there is no proxy-level read timeout, so the provider timeout bounds the answer call. Verify:

```powershell
(Select-String -Path docs\2026-10-19-system-overview.md -Pattern 'nginx').Count   # Expected: 0
```

- [ ] **Step 2: Replace the router-timeout comment in `backend/app/core/config.py`**

Replace the line `# Router timeout sits inside nginx's 60s budget next to the 30s answer call.` with:

```python
    # Router timeout guards the routing call; Caddy imposes no upstream read timeout, so
    # the 30s answer call is bounded only by llm_timeout_seconds.
```

- [ ] **Step 3: Re-anchor the nginx watch items in `docs/backlog.md` and add follow-ups**

Re-anchor the four nginx-anchored items (the `client_max_body_size 26m` upload-window mention, the connect+read worst-case approaching `proxy_read_timeout`, and the `e9c748c` items: bare `/api` fallthrough, `Cache-Control` on `index.html`, proxy timeout overrides) to their Caddy equivalents (`request_body 26MiB`, no default read timeout, `handle /api/*`), keeping each item's underlying concern. Then add a timestamped `## 2026-10-27 - Hetzner deployment follow-ups` section recording: the pre-existing `ruff format --check` findings in 12 old plan docs (run the gates from `backend/` per `AGENTS.md`; reformatting historical plan docs was out of scope), the ACME account email candidate, and the HTTP/3 UDP port candidate (spec section 11), each linking to this branch's commits.

- [ ] **Step 4: Run the backend style gates (config.py comment changed)**

```powershell
D:\Projects\RAG\.venv\Scripts\ruff.exe check backend
D:\Projects\RAG\.venv\Scripts\ruff.exe format --check backend
```

Expected: both pass (comment-only change; mypy/pytest results cannot change because of a comment and are exercised fully in Task 8).

- [ ] **Step 5: Commit (one concern each)**

```powershell
git add docs/2026-10-19-system-overview.md docs/backlog.md
git commit -m "docs: re-anchor the web tier references to Caddy"
git add backend/app/core/config.py
git commit -m "docs(backend): re-anchor the router timeout comment to Caddy"
```

### Task 8: Full gates, spec freeze, and finish

**Files:**
- Modify: `docs/superpowers/specs/2026-10-27-hetzner-deployment-design.md` (Status line only)

**Interfaces:**
- Consumes: every task above; Task 0's venv, node_modules, and stack.

- [ ] **Step 1: Bring the stack current**

```powershell
docker compose -f deploy/docker-compose.yml up -d --build
```

- [ ] **Step 2: Backend gates**

```powershell
cd backend
D:\Projects\RAG\.venv\Scripts\ruff.exe check .
D:\Projects\RAG\.venv\Scripts\ruff.exe format --check .
..\.venv\Scripts\python -m mypy app tests
..\.venv\Scripts\python -m pytest
```

Expected: all four pass. (ruff resolves config from `backend/pyproject.toml`; the worktree venv serves mypy and pytest.)

- [ ] **Step 3: Web gates**

```powershell
cd ..\web
npm run lint
npm run format:check
npm run test
npm run e2e
```

Expected: all pass (e2e spins its own uvicorn/celery fixtures against the compose infra on 5432/5672 - Task 0's stack provides them).

- [ ] **Step 4: Freeze the spec**

Update the spec's Status line to `Design round complete (2026-10-27); implemented (2026-10-27).` and commit:

```powershell
git add docs/superpowers/specs/2026-10-27-hetzner-deployment-design.md
git commit -m "docs: mark the Hetzner deployment spec implemented"
```

- [ ] **Step 5: Leave the machine-global system in a defined state**

```powershell
cd ..
docker compose -f deploy/docker-compose.yml down
```

Note in the handoff: the worktree stack is down; the main checkout owns the next `up` per the README.

- [ ] **Step 6: Finish the branch**

Invoke `superpowers:finishing-a-development-branch` for the merge/review decision.
