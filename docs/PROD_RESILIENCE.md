# Устойчивость prod после перезагрузки VPS

Если после сбоя или ребута **Docker работает**, а **сайт не открывается** — обычно упал **системный nginx** (ISPmanager): в vhost остался старый `listen 192.168.x.x:443`, которого уже нет на сервере.

## Однократно на сервере (рекомендуется)

```bash
cd /opt/aisearch
git pull origin main
sudo bash scripts/setup-prod-resilience.sh
```

Скрипт:

1. Включает автозапуск `nginx` и `docker`
2. Поднимает `docker compose -f docker-compose.prod.yml`
3. Пересобирает vhost app/api/admin с **текущим IP** и `PROXY_PORT` (18080)
4. Ставит cron: проверка через 45 с после reboot и **каждые 5 минут**
5. Пишет лог в `/var/log/glosix-nginx-ensure.log`

## Ручные команды (по шагам)

### Шаг 1. Автозапуск сервисов

```bash
sudo systemctl enable nginx docker
sudo systemctl start docker
```

### Шаг 2. Docker-приложение

```bash
cd /opt/aisearch
docker compose -f docker-compose.prod.yml up -d --remove-orphans
docker compose -f docker-compose.prod.yml ps
```

### Шаг 3. Vhost nginx → Docker (порт 18080)

```bash
cd /opt/aisearch
export PROXY_PORT=18080   # как в hosting.config
sudo bash scripts/fix-nginx-app-glosix.sh
sudo bash scripts/fix-nginx-api-glosix.sh
sudo bash scripts/fix-nginx-admin-glosix.sh
```

### Шаг 4. Проверка и старт nginx

```bash
sudo nginx -t
sudo systemctl start nginx
sudo systemctl status nginx --no-pager
ss -tlnp | grep -E ':443|:80 '
curl -sS -I https://app.glosix.ru/ | head -5
```

### Шаг 5. Cron (защита после смены IP)

```bash
sudo tee /etc/cron.d/glosix-nginx-ensure <<'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
@reboot root sleep 45 && cd /opt/aisearch && /opt/aisearch/scripts/ensure-nginx-glosix.sh >> /var/log/glosix-nginx-ensure.log 2>&1
*/5 * * * * root cd /opt/aisearch && /opt/aisearch/scripts/ensure-nginx-glosix.sh >> /var/log/glosix-nginx-ensure.log 2>&1
EOF
```

Проверка вручную:

```bash
sudo bash /opt/aisearch/scripts/ensure-nginx-glosix.sh
tail -20 /var/log/glosix-nginx-ensure.log
```

## После правок в ISPmanager

Панель может **перезаписать** vhost и снова прописать старый IP. Если сайт пропал:

```bash
cd /opt/aisearch && sudo bash scripts/ensure-nginx-glosix.sh
```

Или полностью перегенерировать три vhost (шаг 3).

## Диагностика

| Команда | Ожидание |
|---------|----------|
| `curl -s http://127.0.0.1:18080/api/health -H 'Host: app.glosix.ru'` | JSON `status: ok` |
| `systemctl is-active nginx` | `active` |
| `curl -sI https://app.glosix.ru/` | `HTTP/2 200` |
| `journalctl -u nginx -n 20` | нет `Cannot assign requested address` |
