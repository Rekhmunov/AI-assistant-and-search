# AI Search — поисковый ассистент для MAX

Perplexity-like мини-приложение в мессенджере MAX: поиск через Yandex Search, ответы через YandexGPT со стримингом, треды, история, тарифы Free/Pro.

## Структура

```
backend/     — FastAPI, PostgreSQL, Redis, Celery
frontend/    — React миниапп (Vite)
admin/       — React SPA для рассылок и метрик
nginx/       — reverse proxy (production)
```

## Быстрый старт (Docker)

```bash
cp .env.example .env
docker compose up --build
```

| Сервис   | URL                    |
|----------|------------------------|
| API      | http://localhost:8000  |
| Miniapp  | http://localhost:5173  |
| Admin    | http://localhost:5174  |
| Swagger  | http://localhost:8000/docs |

В dev-режиме (`SKIP_INIT_DATA_VALIDATION=true`) миниапп входит без реального MAX initData.

## Локальная разработка

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export $(grep -v '^#' ../.env | xargs)
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend && npm install && npm run dev
```

### Admin

```bash
cd admin && npm install && npm run dev
```

## API (основное)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/auth/login` | initData → JWT + refresh cookie |
| POST | `/api/search` | SSE: sources → tokens → follow_ups → done |
| GET | `/api/threads` | История тредов |
| GET | `/api/threads/{id}` | Тред с сообщениями |
| GET | `/api/users/me` | Профиль и лимиты |
| POST | `/api/payments/create` | Создать платёж Pro |
| POST | `/api/payments/dev-activate` | Dev: активировать Pro |

### SSE-события поиска

- `thread` — `{ thread_id }`
- `sources` — `{ sources: [...] }`
- `token` — `{ text }`
- `follow_ups` — `{ questions: [...] }`
- `done` — `{ message_id, searches_today, searches_limit }`
- `error` — `{ code, message }`

## Переменные окружения

См. `.env.example`. Обязательно для production:

- `BOT_TOKEN` — токен бота MAX
- `JWT_SECRET` — секрет для JWT
- `SKIP_INIT_DATA_VALIDATION=false`
- `YANDEX_FOLDER_ID`, `YANDEX_API_KEY` — без них работают mock-источники и ответы
- `ADMIN_API_KEY` — заголовок `X-Admin-Key` для админки

## MAX Bot

Бот должен отвечать на `/start` кнопкой «Открыть приложение» (`openAppButton`). Рассылки запускаются из admin SPA → Celery worker.

## Дальше (не в MVP)

- Полная интеграция ЮKassa
- Webhook бота MAX для `/start`
- i18n EN
- Приоритетная очередь Pro
