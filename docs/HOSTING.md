# Перенос на хостинг (VPS + ISPmanager)

Полный комплект для переноса: Docker, скрипты, шаблоны конфигов, архив для SFTP.

## Содержимое пакета

| Файл / папка | Назначение |
|--------------|------------|
| `docker-compose.prod.yml` | Production-стек |
| `hosting.config.example` | Ваши домены и пути |
| `scripts/configure-hosting.sh` | Генерация `.env` + nginx |
| `scripts/pack-for-hosting.sh` | Архив для загрузки без Git |
| `scripts/deploy.sh` | Автодеплой с GitHub |
| `scripts/backup-db.sh` | Бэкап PostgreSQL |
| `scripts/update.sh` | Обновление версии |
| `scripts/check-hosting.sh` | Проверка после установки |
| `hosting/ispmanager-proxy.conf` | Сниппет для панели |
| `Makefile` | Команды `make up`, `make configure`, … |

---

## Способ A — Git (рекомендуется)

На VPS:

```bash
sudo bash scripts/install-docker.sh

export APP_DIR=/opt/aisearch
git clone -b cursor/initial-service-scaffold-f0d8 \
  https://github.com/Rekhmunov/AI-assistant-and-search.git "$APP_DIR"
cd "$APP_DIR"

cp hosting.config.example hosting.config
nano hosting.config   # DOMAIN, app/api/admin хосты

make configure        # .env + nginx
nano .env             # BOT_TOKEN, Yandex keys

make up
make check
```

Дальше — SSL и прокси в ISPmanager (ниже).

---

## Способ B — Архив по SFTP

На своём ПК (в каталоге проекта):

```bash
bash scripts/pack-for-hosting.sh
# → aisearch-hosting-xxxx.tar.gz
```

Загрузите архив на сервер (`/opt/`), распакуйте:

```bash
mkdir -p /opt/aisearch && tar -xzf aisearch-hosting-*.tar.gz -C /opt/aisearch
cd /opt/aisearch
cp hosting.config.example hosting.config && nano hosting.config
make configure
nano .env
make up
make check
```

---

## DNS

| Запись | Тип | Значение |
|--------|-----|----------|
| `app` | A | IP VPS |
| `api` | A | IP VPS |
| `admin` | A | IP VPS |

---

## ISPmanager

Для **app**, **api**, **admin**:

1. Создать WWW-домен.
2. Выпустить SSL (Let's Encrypt).
3. Вставить прокси из `hosting/ispmanager-proxy.conf` (для **api** обязательно `proxy_buffering off`).

Upstream: `http://127.0.0.1:8080` (или `PROXY_PORT` из `hosting.config`).

---

## MAX

| Параметр | Значение |
|----------|----------|
| URL миниаппа | `https://app.ваш-домен.ru` |
| `BOT_TOKEN` | в `.env` |
| `SKIP_INIT_DATA_VALIDATION` | `false` |

---

## Эксплуатация

```bash
make ps          # статус контейнеров
make logs        # логи API
make backup      # дамп БД в ./backups/
make update      # git pull + пересборка
make down        # остановить
```

Cron бэкап (раз в сутки):

```cron
0 3 * * * cd /opt/aisearch && bash scripts/backup-db.sh >> /var/log/aisearch-backup.log 2>&1
```

---

## Чеклист переноса

- [ ] `hosting.config` заполнен
- [ ] `make configure` выполнен
- [ ] `BOT_TOKEN`, Yandex API в `.env`
- [ ] DNS указывает на VPS
- [ ] `make up` — контейнеры healthy
- [ ] `make check` — без FAIL
- [ ] HTTPS на всех трёх поддоменах
- [ ] `curl https://api.домен/health` → `{"status":"ok"}`
- [ ] URL миниаппа в кабинете MAX
- [ ] Firewall: открыты только 22, 80, 443

Подробности: [DEPLOY.md](./DEPLOY.md)
