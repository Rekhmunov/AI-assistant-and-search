#!/usr/bin/env bash
# Primary IPv4 for ISPmanager listen directives (after reboot IP may change).
set -euo pipefail

if [ -n "${LISTEN_IP:-}" ]; then
  echo "$LISTEN_IP"
  exit 0
fi

ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") print $(i + 1); exit}')"
if [ -z "$ip" ]; then
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
if [ -z "$ip" ]; then
  echo "Cannot detect LISTEN_IP. Export LISTEN_IP=<server-ipv4> and retry." >&2
  exit 1
fi
echo "$ip"
