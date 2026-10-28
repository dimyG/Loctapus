#!/usr/bin/env bash
# Runs on the VPS, invoked by the CI workflow after the workflow's own git pull.
# Never loses state: no down, no down -v, nothing beyond what up recreates.
# Also re-asserts the TCP MSS clamp so every deploy self-heals it.
set -euo pipefail
cd /root/Loctapus
chmod 600 deploy/.env backend/.env

# Clamp the MSS the stack advertises on 80/443 SYN packets down to 1400 bytes.
# Clients on PPPoE or tunnel uplinks whose routers drop the
# fragmentation-needed ICMP never learn the real path MTU, so every request
# body bigger than the initial congestion window (a few hundred KB) stalls
# mid-upload with no error on either side. Advertising a small MSS caps client
# segments below every common reduced-MTU path, so uploads cannot depend on
# PMTUD working. Idempotent: the -C probe skips rules already loaded.
clamp_mss() {
  local chain="$1"
  shift
  if ! iptables -t mangle -C "$chain" "$@" -j TCPMSS --set-mss 1400 2>/dev/null; then
    iptables -t mangle -A "$chain" "$@" -j TCPMSS --set-mss 1400
  fi
}
clamp_mss FORWARD -p tcp --tcp-flags SYN,RST SYN -m multiport --dports 80,443
clamp_mss FORWARD -p tcp --tcp-flags SYN,RST SYN -m multiport --sports 80,443
clamp_mss INPUT -p tcp --tcp-flags SYN,RST SYN -m multiport --dports 80,443
clamp_mss OUTPUT -p tcp --tcp-flags SYN,RST SYN -m multiport --sports 80,443

# Persist the clamp across reboots: ufw loads /etc/ufw/before.rules through
# iptables-restore at every enable, and the block below carries the same four
# rules in restore syntax. The marker makes the append idempotent.
if ! grep -q "BEGIN Loctapus MSS clamp" /etc/ufw/before.rules; then
  cat >> /etc/ufw/before.rules <<'EOF'
# BEGIN Loctapus MSS clamp (added by deploy/hetzner/deploy.sh)
*mangle
-A FORWARD -p tcp --tcp-flags SYN,RST SYN -m multiport --dports 80,443 -j TCPMSS --set-mss 1400
-A FORWARD -p tcp --tcp-flags SYN,RST SYN -m multiport --sports 80,443 -j TCPMSS --set-mss 1400
-A INPUT -p tcp --tcp-flags SYN,RST SYN -m multiport --dports 80,443 -j TCPMSS --set-mss 1400
-A OUTPUT -p tcp --tcp-flags SYN,RST SYN -m multiport --sports 80,443 -j TCPMSS --set-mss 1400
COMMIT
# END Loctapus MSS clamp
EOF
fi

docker compose -f deploy/docker-compose.yml -f deploy/hetzner/docker-compose.server.yml up -d --build
docker image prune -f
