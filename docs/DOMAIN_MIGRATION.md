# Перенос app.glosix.ru → glosix.ru

Миниапп и сайт открываются на **корневом домене** `https://glosix.ru`. Старый `app.glosix.ru` — **301** на новый URL. `api.glosix.ru` отвечает на `/` (не 404).

## 1. DNS (REG.RU)

| Имя | Тип | Значение |
|-----|-----|----------|
| `@` | A | IP VPS |
| `www` | A | IP VPS (или CNAME → glosix.ru) |
| `api` | A | IP VPS |
| `admin` | A | IP VPS |
| `app` | A | IP VPS (для редиректа) |

Проверка: `dig +short glosix.ru`

## 2. hosting.config на сервере

```bash
cd /opt/aisearch
nano hosting.config
```

```bash
DOMAIN=glosix.ru
APP_HOST=glosix.ru
APP_HOST_ALIASES=www.glosix.ru
LEGACY_APP_HOST=app.glosix.ru
API_HOST=api.glosix.ru
ADMIN_HOST=admin.glosix.ru
PROXY_PORT=18080   # ваш порт Docker-nginx
```

Пересобрать внутренний nginx:

```bash
bash scripts/render-nginx.sh
docker compose -f docker-compose.prod.yml up -d --force-recreate nginx
```

## 3. .env (вручную, не перезаписывать configure-hosting)

Добавьте/обновите:

```bash
VITE_PUBLIC_URL=https://glosix.ru
CORS_ORIGINS=https://glosix.ru,https://www.glosix.ru,https://api.glosix.ru,https://admin.glosix.ru,https://app.glosix.ru
COOKIE_DOMAIN=.glosix.ru
```

Пересборка frontend:

```bash
bash scripts/update-prod.sh
```

## 4. ISPmanager (внешний nginx)

```bash
sudo bash scripts/fix-nginx-glosix-root.sh      # glosix.ru + www → Docker
sudo bash scripts/fix-nginx-app-glosix.sh       # app.glosix.ru → 301 glosix.ru
sudo bash scripts/fix-nginx-api-glosix.sh       # api (если ещё не прокси)
sudo bash scripts/fix-nginx-admin-glosix.sh     # admin (если нужно)
```

В ISPmanager: WWW-домен **glosix.ru**, SSL Let's Encrypt.

## 5. MAX

В кабинете бота обновите URL миниаппа на **`https://glosix.ru`**.

## 6. Проверка

```bash
curl -s https://glosix.ru/api/health
curl -sI https://app.glosix.ru/ | grep -i location   # → glosix.ru
curl -s https://api.glosix.ru/                         # {"status":"ok",...}
curl -s https://api.glosix.ru/health                   # {"status":"ok"}
bash scripts/verify-deploy.sh
```

## api.glosix.ru

`GET https://api.glosix.ru/` → **404** (пустая корневая страница, без JSON).

Рабочие пути: `/health`, `/api/health`, `/api/*`.
