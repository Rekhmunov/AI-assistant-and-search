#!/usr/bin/env bash
# Однократная настройка: автозапуск nginx/docker + cron-проверка vhost после ребута.
# Запуск на VPS: cd /opt/aisearch && sudo bash scripts/setup-prod-resilience.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ "$(id -u)" -ne 0 ]; then
  echo "Запустите с sudo: sudo bash scripts/setup-prod-resilience.sh"
  exit 1
fi

if [ -f hosting.config ]; then
  # shellcheck disable=SC1091
  source hosting.config
fi
PROXY_PORT="${PROXY_PORT:-18080}"
export PROXY_PORT

echo "==> 1/5 Автозапуск nginx и docker"
systemctl enable nginx
systemctl enable docker
systemctl start docker

echo "==> 2/5 Docker stack (prod)"
if [ -f docker-compose.prod.yml ]; then
  docker compose -f docker-compose.prod.yml up -d --remove-orphans
else
  echo "WARN: нет docker-compose.prod.yml в $ROOT"
fi

echo "==> 3/5 Vhost app/api/admin (актуальный IP + порт $PROXY_PORT)"
if [ -x "$ROOT/scripts/fix-nginx-app-glosix.sh" ]; then
  bash "$ROOT/scripts/fix-nginx-app-glosix.sh" || true
  bash "$ROOT/scripts/fix-nginx-api-glosix.sh" || true
  bash "$ROOT/scripts/fix-nginx-admin-glosix.sh" || true
else
  bash "$ROOT/scripts/ensure-nginx-glosix.sh"
fi

echo "==> 4/5 Cron: проверка nginx после загрузки и каждые 5 минут"
CRON_FILE="/etc/cron.d/glosix-nginx-ensure"
cat >"$CRON_FILE" <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
@reboot root sleep 45 && cd ${ROOT} && ${ROOT}/scripts/ensure-nginx-glosix.sh >> /var/log/glosix-nginx-ensure.log 2>&1
*/5 * * * * root cd ${ROOT} && ${ROOT}/scripts/ensure-nginx-glosix.sh >> /var/log/glosix-nginx-ensure.log 2>&1
EOF
chmod 644 "$CRON_FILE"
touch /var/log/glosix-nginx-ensure.log

echo "==> 5/5 Финальная проверка"
bash "$ROOT/scripts/ensure-nginx-glosix.sh"
if [ -x "$ROOT/scripts/verify-deploy.sh" ]; then
  sudo -u "${SUDO_USER:-root}" bash "$ROOT/scripts/verify-deploy.sh" || true
fi

echo ""
echo "Готово."
echo "  Лог cron: tail -f /var/log/glosix-nginx-ensure.log"
echo "  Ручная проверка: sudo bash scripts/ensure-nginx-glosix.sh"
