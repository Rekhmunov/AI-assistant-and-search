# Деплой на VPS (REG.RU + ISPmanager)

> **Быстрый старт переноса:** [HOSTING.md](./HOSTING.md) · чеклист [HOSTING_CHECKLIST.md](../HOSTING_CHECKLIST.md)

## Готово ли в репозитории?

| Компонент | Статус |
|-----------|--------|
| Backend, frontend, admin | ✅ |
| `docker-compose.prod.yml` | ✅ production |
| Миграции Alembic | ✅ |
| Nginx внутри Docker | ✅ `127.0.0.1:8080` |
| SSL | ⚙️ через ISPmanager (Let's Encrypt) |
| Домен в MAX / бот `/start` | ⚙️ настраиваете вы |

**Итого:** код готов; на сервере нужны Docker, `.env`, домены и прокси в ISPmanager.

---

## Архитектура

```text
Интернет → ISPmanager (HTTPS :443)
              ↓ reverse proxy
         127.0.0.1:8080 (Docker nginx)
              ├── app.ваш-домен.ru  → frontend (миниапп)
              ├── api.ваш-домен.ru  → backend (API + SSE)
              └── admin.ваш-домен.ru → admin
         postgres, redis — только внутри Docker (наружу не открыты)
```

Рекомендуем **3 поддомена**:

- `app.` — миниапп (URL в MAX)
- `api.` — бэкенд
- `admin.` — рассылки

---

## 1. Подготовка VPS

Подключитесь по SSH:

```bash
ssh root@ВАШ_IP
```

Установите Docker (Ubuntu):

```bash
apt update && apt install -y git
cd /tmp
git clone --branch cursor/initial-service-scaffold-f0d8 \
  https://github.com/Rekhmunov/AI-assistant-and-search.git aisearch-src
cd aisearch-src
sudo bash scripts/install-docker.sh
```

---

## 2. DNS

В REG.RU для домена создайте A-записи на IP VPS:

| Имя | Тип | Значение |
|-----|-----|----------|
| `app` | A | IP VPS |
| `api` | A | IP VPS |
| `admin` | A | IP VPS |

Админка: вход по email/паролю (`ADMIN_BOOTSTRAP_*` в `.env`, первый запуск создаёт owner). В `CORS_ORIGINS` должен быть `https://admin.ваш-домен`.

Подождите 5–30 минут, проверьте: `dig +short app.ваш-домен.ru`

---

## 3. Клонирование и конфиг

```bash
sudo mkdir -p /opt/aisearch
sudo git clone --branch cursor/initial-service-scaffold-f0d8 \
  https://github.com/Rekhmunov/AI-assistant-and-search.git /opt/aisearch
cd /opt/aisearch

cp .env.production.example .env
nano .env
```

### Обязательно в `.env`

```bash
# Секреты (на сервере):
openssl rand -hex 32   # → JWT_SECRET
openssl rand -hex 24   # → ADMIN_API_KEY, POSTGRES_PASSWORD

VITE_API_URL=https://api.ваш-домен.ru
BOT_TOKEN=токен_бота_MAX
SKIP_INIT_DATA_VALIDATION=false
CORS_ORIGINS=https://app.ваш-домен.ru,https://api.ваш-домен.ru
ENVIRONMENT=production
DEBUG=false
```

Добавьте ключи Yandex Cloud для боевого поиска и GPT — пошагово в [YANDEX_SETUP.md](./YANDEX_SETUP.md). Проверка: `curl https://api.ваш-домен.ru/api/health/yandex`.

### Домены в nginx

```bash
nano nginx/nginx.prod.conf
```

Замените `app.example.com`, `api.example.com`, `admin.example.com` на ваши хосты.

---

## 4. Запуск Docker

```bash
cd /opt/aisearch
chmod +x scripts/deploy.sh
sudo bash scripts/deploy.sh
```

Проверка внутри сервера:

```bash
curl -s http://127.0.0.1:8080/health -H "Host: api.ваш-домен.ru"
# ожидается: {"status":"ok"}
```

Логи:

```bash
docker compose -f docker-compose.prod.yml logs -f backend
```

---

## 5. ISPmanager — reverse proxy + SSL

Для **каждого** поддомена (`app`, `api`, `admin`):

1. **WWW-домены** → создать сайт на этот поддомен.
2. **SSL** → Let's Encrypt (включить HTTPS).
3. **Настройки nginx** (или «Проксирование») — upstream на приложение:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_read_timeout 300s;
}
```

Для `api` обязательно `proxy_buffering off` (SSE-стриминг).

4. Убедитесь, что **порты 80 и 443** слушает ISPmanager, а **не** второй nginx из Docker наружу (в `docker-compose.prod.yml` nginx привязан только к `127.0.0.1:8080` — конфликта нет).

---

## 6. MAX — миниапп и бот

1. В кабинете MAX: URL миниаппа = `https://app.ваш-домен.ru`
2. Бот: `/start` + кнопка «Открыть приложение» на этот URL.
3. `BOT_TOKEN` в `.env` совпадает с ботом, для которого выдан initData.

Проверка API снаружи:

```bash
curl https://api.ваш-домен.ru/health
```

---

## 7. Обновление релиза

```bash
cd /opt/aisearch
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

---

## 8. Firewall

```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

PostgreSQL (5432) и Redis **не** открывайте наружу.

---

## Частые проблемы

| Симптом | Решение |
|---------|---------|
| 502 Bad Gateway | `docker compose -f docker-compose.prod.yml ps`, логи backend |
| CORS error в миниаппе | `CORS_ORIGINS` должен содержать `https://app...` |
| Invalid initData | `SKIP_INIT_DATA_VALIDATION=false`, верный `BOT_TOKEN` |
| SSE обрывается | `proxy_buffering off`, `proxy_read_timeout 300s` на api |
| Сборка frontend старый API | После смены `VITE_API_URL` — `docker compose ... build --no-cache frontend admin` |

---

## Чеклист перед открытием пользователям

- [ ] HTTPS на app и api
- [ ] `JWT_SECRET` и пароли не дефолтные
- [ ] `SKIP_INIT_DATA_VALIDATION=false`
- [ ] Yandex API ключи (или осознанно mock)
- [ ] Бэкап VPS / PostgreSQL
- [ ] URL миниаппа прописан в MAX
