# Чеклист переноса на хостинг

## Перед загрузкой

- [ ] Домен куплен, доступ к DNS REG.RU
- [ ] VPS доступен по SSH
- [ ] Токен бота MAX
- [ ] (Опционально) Ключи Yandex Cloud

## На сервере

- [ ] `sudo bash scripts/install-docker.sh`
- [ ] Проект в `/opt/aisearch` (git clone или `tar` из `make pack`)
- [ ] `cp hosting.config.example hosting.config` → заполнить домены
- [ ] `make configure`
- [ ] `nano .env` → `BOT_TOKEN`, Yandex
- [ ] `make up`
- [ ] `make check` — без FAIL

## ISPmanager

- [ ] Сайты: app / api / admin
- [ ] SSL Let's Encrypt на каждый
- [ ] Proxy → `127.0.0.1:8080` (`hosting/ispmanager-proxy.conf`)
- [ ] На **api**: `proxy_buffering off`, timeout 300s

## MAX

- [ ] Миниапп URL = `https://app.ваш-домен`
- [ ] `curl https://api.ваш-домен/health` → ok

## После запуска

- [ ] Cron: `scripts/backup-db.sh`
- [ ] (Опционально) `systemctl enable` → `systemd/aisearch.service`

Подробно: [docs/HOSTING.md](docs/HOSTING.md)
