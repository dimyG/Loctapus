#!/usr/bin/env bash
# One-shot provisioning of a fresh Hetzner VPS for the RAG demo: Docker, swap,
# firewall, the repo clone, the CI deploy key, and the host-key pin. Run once,
# as root. No secret values live here - they all arrive via the first deploy.
set -euo pipefail

public_key_file="${1:?usage: bootstrap.sh <ci-deploy-public-key-file>}"

# The script runs as `curl ... | bash -s` over a non-interactive SSH session, so
# its stdin is the script itself; a package prompt must never read that stdin.
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get upgrade -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# Build headroom on a 4 GB box.
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Firewall: SSH plus the published web ports (443/udp carries HTTP/3).
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

# The application tree (public repository, no credentials needed).
git clone https://github.com/dimyG/Loctapus.git /root/Loctapus

# The CI deploy key: its private half only ever lives in GitHub secrets.
mkdir -p /root/.ssh
chmod 700 /root/.ssh
cat "$public_key_file" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

# Pre-create the env files the CI renders into, so the first scp writes into
# 600-mode files instead of creating world-readable ones.
install -m 600 /dev/null /root/Loctapus/deploy/.env
install -m 600 /dev/null /root/Loctapus/backend/.env

# The host-key pin: keyed by the public IPv4 the CI connects to.
public_ip="$(curl -fsS http://169.254.169.254/hetzner/v1/metadata/public-ipv4)"
echo "Paste the following line into the HETZNER_KNOWN_HOSTS secret,"
echo "and set HETZNER_HOST to the same address:"
ssh-keyscan -t ed25519 "$public_ip"
