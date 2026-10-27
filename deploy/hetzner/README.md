# Hetzner demo deployment - operator runbook

This is the runbook for the single-VPS demo deployment of the RAG system: one Hetzner
box, Docker Compose, Caddy on 80/443 with automatic HTTPS, and a GitHub Actions
workflow that redeploys on every push to `master`. It is explicitly not a production
platform: no backups, no zero-downtime, throwaway demo data.

## Bootstrap vs deploy

Two scripts with different lifecycles and duties:

- **Bootstrap** (`deploy/hetzner/bootstrap.sh`) runs once per VPS, by hand, as root. It
  installs Docker, creates a 2 GB swapfile, configures the ufw firewall (22, 80, 443),
  clones the repository to `/root/Loctapus`, installs the CI deploy key, pre-creates the two
  env files with mode 600, and prints the `ssh-keyscan` host-key pin. It holds no
  secret values - every credential arrives via the first deploy.
- **Deploy** (`.github/workflows/deploy.yml` -> `deploy/hetzner/deploy.sh`) runs on
  every push to `master`, automatically. It renders `deploy/.env` and `backend/.env`
  from the GitHub secrets, copies them to the server, pulls the branch, and runs
  `docker compose up -d --build` with the server override. It only ever touches the
  checkout and the Docker images.

Bootstrap ever runs again only on a rebuilt VPS. Invocation recipe (the repository is
not cloned yet when bootstrap runs, so fetch it from raw GitHub):

```
ssh-keygen -t ed25519 -f ci_deploy -N ""   # local; the private half becomes HETZNER_SSH_KEY
scp ci_deploy.pub root@<server-ip>:/root/ci_deploy.pub
ssh root@<server-ip> 'curl -fsSL https://raw.githubusercontent.com/dimyG/Loctapus/master/deploy/hetzner/bootstrap.sh | bash -s /root/ci_deploy.pub'
```

Honest privilege note: the CI key sits in root's `authorized_keys`, so it is a full
root key by design - the bootstrap/deploy separation is operational (what each script
does and how often it runs), not an enforcement boundary. The optional
`command="..."` restriction on the CI key's `authorized_keys` line (limiting it to the
exact deploy invocation) is available as hardening if that bothers you.

## Prerequisites and setup order

1. **Hetzner console**: create the VPS - CX23 (2 vCPU, 4 GB RAM, 40 GB disk, about
   EUR 6 per month with the primary IPv4), Ubuntu 24.04, your personal SSH key.
   Availability caveat: Hetzner's budget line (CX23, and the ARM alternative CAX11)
   cycles in and out of stock; if it is unorderable, wait for a restock or fall back
   to a Regular Performance CPX server (about EUR 20 per month).
2. **Bootstrap**: run `bootstrap.sh` on the box (recipe above). It prints the
   host-key pin at the end.
3. **GitHub secrets**: create all 17 secrets from the table below. Generate the
   passwords, secrets, and tokens with `openssl rand -hex 32`; keep usernames and
   passwords URL-safe (no `: / @ # ?`) because they interpolate into
   `RAG_DATABASE_URL` and `RAG_BROKER_URL`. Two secrets are not random strings:
   `STACK_GARAGE_DEFAULT_BUCKET` is a plain bucket name (lowercase, 3-63 characters,
   e.g. `rag-demo` - Garage refuses invalid names and every upload would fail), and
   `STACK_SITE_ADDRESS` is the demo domain.
4. **DNS**: create an A record for the demo domain pointing at the VPS. Any AAAA
   record must also point at the VPS or be absent, or ACME validation can fail.
5. **First deploy**: push to `master`, or trigger the workflow manually
   (`workflow_dispatch`). The first run renders the env files, ships them over, and
   builds the stack; Caddy obtains the Let's Encrypt certificate on the first start.

### GitHub Actions secrets

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
`X`), and the `APP_` prefix is stripped (`APP_RAG_JWT_SECRET` -> `RAG_JWT_SECRET`).
`RAG_LLM_PROVIDER=groq` is derived from the Groq key's presence, and
`RAG_ENVIRONMENT=production` is a fixed render line that reaches the api container
only (it is the only service that mounts `backend/.env`).

## Data persistence

What survives every deploy: everything. All state lives in named volumes - `pgdata`
(users, workspaces, projects, chunks, chat history), `rabbitmqdata`, `garagemeta` and
`garagedata` (uploaded document bytes), `caddydata` (certificates). `up -d --build`
rebuilds images and recreates changed containers only; named volumes are untouched.
Schema changes ride along: compose `up` starts the exited `one-off-initialization`
container again, so migrations run on every deploy - harmless, because
`alembic upgrade head` is a no-op on an up-to-date schema, and new revisions apply
forward-only, data-preserving changes to the existing `pgdata`.

The exhaustive list of destructive actions:

| Action | Volumes |
| --- | --- |
| Every CI deploy (`up -d --build`) | kept |
| `docker compose down` | kept |
| `docker compose down -v` | wiped |
| Deleting the VPS in the Hetzner console | wiped |

`deploy.sh` never contains `down` or `down -v` - that is the never-loses-state
invariant, and it is checked in review.

## Secrets transport and rotation

Nothing crosses a wire in plaintext. GitHub-to-runner is HTTPS (the step's `env:`
mapping carries the values); runner-to-server is SSH. At GitHub, secrets are
encrypted at rest with logged access and are readable only by workflows that
reference them. On the server, the `.env` files are plaintext by necessity (compose
reads them), protected by 600 root-only permissions on a single-tenant box - the same
model as the local dev copies. `deploy.sh` re-asserts the permissions on every deploy.

Host-key pinning: the workflow pins the server's SSH host key. Paste the
`ssh-keyscan` line bootstrap printed into the `HETZNER_KNOWN_HOSTS` secret, and set
`HETZNER_HOST` to that same IP - the pin is keyed by the exact address the runner
connects to. A host-key mismatch stops the deploy (no trust-on-first-use). After a
VPS rebuild the host key legitimately changes; re-populate the secret then.

Rotation rules:

- `STACK_*` credentials: rotate only together with fresh volumes. Garage binds its
  stored layout to `GARAGE_DEFAULT_SECRET_KEY` on an initialized volume; Postgres and
  RabbitMQ keep the credentials an initialized volume was created with. Rotating
  these on a live box is a documented "don't".
- `APP_RAG_JWT_SECRET`: rotates freely; it only invalidates outstanding tokens.
  Re-run the workflow to re-render.
- `APP_RAG_GROQ_API_KEY`: rotates freely. Re-run the workflow to re-render.

## Operations

- **Redeploys**: push to `master`, or run the workflow manually via
  `workflow_dispatch` (also the way to re-render the env files after rotating a
  secret, with no code change).
- **Pending runs**: deploys serialize (a compose up is never killed mid-flight). At
  most one run waits; a newer pending run replaces an older one, which is harmless
  because the pull always fetches the branch tip.
- **Admin UIs**: the RabbitMQ management UI and the Garage admin API are not
  published on the server (only web's 80/443 are). Reach them through SSH with a
  loopback-only socat forward on the box:

  ```
  ssh root@<server-ip>
  docker run -d --rm --name admin-ui --network rag_default -p 127.0.0.1:15672:15672 alpine/socat tcp-listen:15672,fork,reuseaddr tcp:rabbitmq:15672
  # then, from the local machine: ssh -N -L 15672:localhost:15672 root@<server-ip>
  # browse http://localhost:15672 ; stop the forward with: docker rm -f admin-ui
  ```

  The same pattern with `3903:3903` and `tcp:garage:3903` reaches the Garage admin.
- **Teardown**: delete the VPS in the Hetzner console. That deletes all data
  (section above); snapshot first if you want anything back.
- **Rebuilding the VPS**: bootstrap again on the fresh box, re-populate
  `HETZNER_KNOWN_HOSTS` from the new keyscan output, and run the workflow once -
  fresh volumes accept the same rendered secrets, so no secret changes are needed.

The design rationale behind every choice here lives in
`docs/superpowers/specs/2026-10-27-hetzner-deployment-design.md`.
