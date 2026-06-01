# Perplexity Sonar в Glosix

## .env

```bash
PERPLEXITY_API_KEY=pplx-xxxxxxxx
PERPLEXITY_MODEL_LITE=sonar
# sonar-pro пока не используется — все вызовы идут в sonar
PERPLEXITY_MODEL_PRO=sonar-pro
```

Имя переменной **строго** `PERPLEXITY_API_KEY` (не `PPLX_API_KEY`).

Формат строки без пробелов вокруг `=`:

```bash
PERPLEXITY_API_KEY=pplx-abc123
```

## Подхват ключа в Docker

После правки `.env` обязательно **пересоздать** backend и worker (обычный `up -d` не подхватывает новые переменные):

```bash
cd /opt/aisearch
docker compose -f docker-compose.prod.yml up -d --force-recreate backend worker
```

Или полное обновление:

```bash
bash scripts/update-prod.sh
```

## Проверка

```bash
curl -s https://api.glosix.ru/health | jq '{perplexity_configured, perplexity_models, llm_runtime}'
```

Ожидается `"perplexity_configured": true`.

Тест API:

```bash
curl -s https://api.glosix.ru/health/perplexity
```

## Админка

LLM → **Perplexity Sonar** → Сохранить.

При `llm_provider=perplexity` Yandex Search и Search Planner не используются — поиск встроен в Sonar.
