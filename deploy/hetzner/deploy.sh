#!/usr/bin/env bash
# Runs on the VPS, invoked by the CI workflow after the workflow's own git pull.
# Never loses state: no down, no down -v, nothing beyond what up recreates.
set -euo pipefail
cd /root/RAG
chmod 600 deploy/.env backend/.env
docker compose -f deploy/docker-compose.yml -f deploy/hetzner/docker-compose.server.yml up -d --build
docker image prune -f
