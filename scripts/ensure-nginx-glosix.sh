#!/usr/bin/env bash
# Починка/проверка внешнего nginx (ISPmanager) для app/api/admin.glosix.ru.
# Безопасно запускать вручную и из cron (@reboot).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -f hosting.config ]; then
  # shellcheck disable=SC1091
  source hosting.config
fi
PROXY_PORT="${PROXY_PORT:-18080}"

LISTEN_IP="$("$ROOT/scripts/nginx-listen-ip.sh")"
VHOST_DIR="${NGINX_VHOST_DIR:-/etc/nginx/vhosts/www-root}"
GLOB="${VHOST_GLOB:-*glosix*.conf}"

log() { echo "[ensure-nginx] $*"; }

if [ ! -d "$VHOST_DIR" ]; then
  log "WARN: нет каталога $VHOST_DIR — пропуск"
  exit 0
fi

mapfile -t CONF_FILES < <(find "$VHOST_DIR" -maxdepth 1 -name "$GLOB" 2>/dev/null | sort)
if [ "${#CONF_FILES[@]}" -eq 0 ]; then
  log "WARN: нет vhost $VHOST_DIR/$GLOB"
  exit 0
fi

# IP, которые реально есть на интерфейсах
mapfile -t LOCAL_IPS < <(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | sort -u)

_ip_is_local() {
  local ip="$1"
  for local in "${LOCAL_IPS[@]}"; do
    [ "$ip" = "$local" ] && return 0
  done
  return 1
}

fix_conf() {
  local conf="$1"
  local changed=0
  local tmp
  tmp="$(mktemp)"

  while IFS= read -r line; do
    new_line="$line"
    if [[ "$line" =~ listen[[:space:]]+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+):([0-9]+) ]]; then
      lip="${BASH_REMATCH[1]}"
      lport="${BASH_REMATCH[2]}"
      if ! _ip_is_local "$lip"; then
        new_line="${line/$lip/$LISTEN_IP}"
        log "  $conf: listen $lip:$lport -> $LISTEN_IP:$lport"
        changed=1
      fi
    fi
    if [[ "$line" == *proxy_pass*127.0.0.1:* ]]; then
      if [[ "$line" != *"127.0.0.1:${PROXY_PORT}"* ]]; then
        new_line="$(echo "$line" | sed -E "s|proxy_pass http://127\\.0\\.0\\.1:[0-9]+|proxy_pass http://127.0.0.1:${PROXY_PORT}|")"
        log "  $conf: proxy_pass -> 127.0.0.1:${PROXY_PORT}"
        changed=1
      fi
    fi
    printf '%s\n' "$new_line"
  done <"$conf" >"$tmp"

  if [ "$changed" -eq 1 ]; then
    cp "$conf" "${conf}.bak.$(date +%s)"
    mv "$tmp" "$conf"
  else
    rm -f "$tmp"
  fi
}

log "LISTEN_IP=$LISTEN_IP PROXY_PORT=$PROXY_PORT"
for conf in "${CONF_FILES[@]}"; do
  fix_conf "$conf"
done

if ! nginx -t 2>/dev/null; then
  log "ERROR: nginx -t failed after patch — проверьте конфиги вручную"
  nginx -t || true
  exit 1
fi

if systemctl is-active --quiet nginx; then
  systemctl reload nginx
  log "nginx: reload OK"
else
  systemctl start nginx
  log "nginx: started"
fi

# Быстрая проверка 443
if ss -tln | grep -q ':443 '; then
  log "OK: порт 443 слушается"
else
  log "WARN: 443 не слушается — проверьте listen в vhost"
  exit 1
fi
