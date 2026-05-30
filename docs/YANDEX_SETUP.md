# Подключение Yandex Search, YandexGPT Lite и Pro

Glosix использует три сервиса Yandex Cloud:

| Сервис | Назначение | Переменные |
|--------|------------|------------|
| **Search API** | Веб-поиск, источники `[1][2]` | `YANDEX_FOLDER_ID`, `YANDEX_API_KEY` |
| **YandexGPT Lite** | Классификатор запросов, обычные ответы | те же + `YANDEX_GPT_LITE_MODEL` |
| **YandexGPT Pro** | Сложные запросы, вложения | те же + `YANDEX_GPT_PRO_MODEL` |

Без ключей в `.env` работает **mock-режим** (фиктивные источники и текст).

---

## 1. Yandex Cloud

1. Войдите в [console.yandex.cloud](https://console.yandex.cloud).
2. Создайте **каталог** (folder) или используйте существующий.
3. Скопируйте **Folder ID** (например `b1gxxxxxxxxxx`).

---

## 2. Сервисный аккаунт и роли

Создайте сервисный аккаунт в этом каталоге и назначьте роли:

| Роль | Зачем |
|------|--------|
| `search-api.webSearch.user` | Веб-поиск Search API v2 |
| `ai.languageModels.user` | YandexGPT Lite и Pro (completion) |

Не используйте устаревшие `search-api.executor`, `search-api.editor`, `search-api.admin`.

В консоли: **Search API** → включить API в каталоге.  
**Yandex AI Studio / Foundation Models** → доступ к моделям в каталоге.

---

## 3. API-ключ

1. **Сервисные аккаунты** → ваш аккаунт → **Создать API-ключ**.
2. Ограничения (scopes), если доступны:
   - поиск: `yc.search-api.execute`
   - GPT: `yc.ai.languageModels.execute` (или эквивалент для Foundation Models)
3. Сохраните ключ — он показывается один раз.

---

## 4. Переменные в `.env` на VPS

В `/opt/aisearch/.env`:

```bash
YANDEX_FOLDER_ID=b1gxxxxxxxxxx
YANDEX_API_KEY=AQVNxxxxxxxxxxxxxxxx

# По умолчанию (можно не менять):
YANDEX_GPT_LITE_MODEL=yandexgpt-lite/latest
YANDEX_GPT_PRO_MODEL=yandexgpt/latest
YANDEX_SEARCH_URL=https://searchapi.api.cloud.yandex.net/v2/web/search
```

Для **YandexGPT 5.1 Pro (RC)** вместо стабильной Pro:

```bash
YANDEX_GPT_PRO_MODEL=yandexgpt/rc
```

---

## 5. Перезапуск и проверка

```bash
cd /opt/aisearch
git pull origin main
docker compose -f docker-compose.prod.yml up -d --build backend
```

Проверка конфигурации (без вызова API):

```bash
curl -s https://app.glosix.ru/api/health | jq '.yandex_configured, .yandex_models'
```

Полная проверка Search + Lite + Pro (~30 с):

```bash
curl -s https://app.glosix.ru/api/health/yandex | jq
```

Ожидаемый ответ при успехе:

```json
{
  "configured": true,
  "search_ok": true,
  "gpt_lite_ok": true,
  "gpt_pro_ok": true,
  "ok": true
}
```

Или с хоста внутри Docker:

```bash
docker compose -f docker-compose.prod.yml exec backend \
  curl -s http://localhost:8000/api/health/yandex
```

---

## 6. Как это работает в приложении

1. Вопрос пользователя → **роутер** (правила + YandexGPT Lite).
2. Если нужен веб-поиск → **Yandex Search** → источники в SSE.
3. Ответ стримится через **YandexGPT Lite** или **Pro** (`answer_model` в событии `route`).
4. В миниаппе бейдж: «Поиск в интернете» / «Ответ по диалогу» · Lite/Pro.
5. **Голосовой ввод в MAX** — запись через `MediaRecorder` в WebView, распознавание на сервере через **SpeechKit STT** (`POST /api/voice/transcribe`). Отдельного API записи голоса в MAX Bridge нет.

---

## 7. SpeechKit STT (голос в миниаппе MAX)

MAX не предоставляет API распознавания речи — только стандартный доступ к микрофону (`getUserMedia`). Backend конвертирует webm/mp4 в OggOpus через **ffmpeg** и отправляет в Yandex SpeechKit.

**Роли сервисного аккаунта / scope API-ключа:**

- `ai.speechkit-stt.user` (или `yc.ai.speechkitStt.execute`)

Проверка:

```bash
curl -s https://app.glosix.ru/api/health/yandex | jq '.stt_ok, .errors'
```

Если `stt_ok: false` и в `errors` есть `stt HTTP 403` — добавьте роль STT тому же ключу, что используется для Search/GPT.

---

## Частые ошибки

| Симптом | Решение |
|---------|---------|
| `yandex_configured: false` | Заполните `YANDEX_FOLDER_ID` и `YANDEX_API_KEY`, пересоберите backend |
| `search HTTP 403` | Роль `search-api.webSearch.user`, включён Search API в каталоге |
| `gpt_lite HTTP 403` | Роль `ai.languageModels.user`, биллинг AI Studio |
| `stt HTTP 403` / `stt_ok: false` | Роль `ai.speechkit-stt.user` (или scope `yc.ai.speechkitStt.execute`) для API-ключа |
| Голос в MAX: «Сервис распознавания речи временно недоступен» | Проверьте `/api/health/yandex` → `stt_ok`; логи backend (`Yandex STT HTTP …`) |
| `gpt_pro HTTP 404` | Смените `YANDEX_GPT_PRO_MODEL` на `yandexgpt/latest` или `yandexgpt/rc` |
| Mock-источники (habr, wikipedia) | Ключи пустые или не подхватились — проверьте `env_file: .env` в compose |
| SSE `yandex_error` | Смотрите `docker compose ... logs backend` |

---

## Админка

В дашборде админки поле **yandex_configured** отражает наличие переменных (не live-probe).
