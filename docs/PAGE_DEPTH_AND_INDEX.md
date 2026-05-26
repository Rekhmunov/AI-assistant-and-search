# Глубина страниц и накопление индекса

## Маршрутизация (контекст через rewriter)

Перед поиском **QueryRewriter** (LLM) возвращает JSON: `intent`, `fact_slots`, `search_queries`.

- **Нет** веток `if погода / elif валюта` по ключевым словам в `search_flow`.
- `fact_slots`: `fx_rate` | `weather_now` | `company_financial` | `course_program` | `[]`
- ЦБ, ранжирование погоды/FX, строгий retrieval — только если слот выставил rewriter.
- `enhance_search_query` — только how-to / опечатки; формулировки поиска задаёт rewriter.

## Текущая модель (v5 + deep pages + Redis cache)

1. Yandex Search — **находит URL** и даёт passage.
2. `fetch_page_full_text` — Redis `page_cache` (gzip) или HTTP:
   - до **48k** символов в кэш, **56 KB** сжатый максимум на ключ;
   - TTL: погода 1ч, ЦБ 30м, новости 6ч, справочники 72ч, остальное 48ч;
   - не кэшируем: PDF, соцсети, login, текст < 400 символов.
3. `enrich_sources_deep` — чанки ~900 символов, топ **4–5** под запрос.
4. `extract` → FactPack → `answer`.

В `debug_trace`: `page_cache: { hits, misses, fetched }`.

Ускорение (env, по умолчанию включено):

| Переменная | Эффект |
|------------|--------|
| `PAGE_FETCH_MAX_CONCURRENT=5` | параллельная загрузка страниц |
| `PAGE_FETCH_MAX_PAGES=5` | меньше HTTP на обычных запросах (8 — pro/финансы/course) |
| `PAGE_FETCH_SKIP_RICH_SNIPPET_CHARS=1400` | не качать URL, если сниппет Search уже длинный |
| `SEARCH_PARALLEL_EXTRA_QUERIES=true` | 2–3-й запрос Yandex параллельно, если первый слабый |
| `FOLLOW_UPS_DEFERRED=true` | `done` раньше, follow-up через ~1 с |

Отключить кэш: `PAGE_CACHE_ENABLED=false` в `.env`.

Проверка: `GET /api/health/page-cache`.

## Свой индекс (поэтапно)

### Уровень 0 — только live fetch

Без Redis (если кэш выключен).

### Уровень 1 — кэш URL в Redis (внедрено)

Ключ `pc:v1:{sha256(url)}`, значение gzip(text), TTL по типу домена.

### Уровень 2 — индекс «вопрос → URL» (внедрено)

Таблица `query_url_log` (Postgres):

| Поле | Назначение |
|------|------------|
| `query_key` | SHA-256 нормализованного запроса (64 символа) |
| `normalized_query` | текст до 512 символов (для отладки) |
| `url_hash` + `url` | дедуп URL, до 2048 символов |
| `score`, `hit_count`, `last_used_at` | ранжирование и свежесть |

Поведение:

- после удачного ответа (retrieval ok или есть факты) — до **5** URL, не более **8** на один `query_key`;
- при новом запросе — до **4** bootstrap URL **до** Yandex Search (по `query_key` основного и первого rewrite);
- те же фильтры URL, что у `page_cache` (без PDF/соцсетей/login).

Отключить: `QUERY_URL_INDEX_ENABLED=false`. Проверка: `GET /api/health/query-url-index`.

Миграция: `alembic upgrade head` (revision `007`).

В `debug_trace`: `query_url_memory: { bootstrap, recorded, lookup_keys }`.

Это не полнотекстовый индекс, а **память сервиса** на ваших пользователях (~200 байт на пару query+url).

### Уровень 3 — чанки + эмбеддинги (Yandex Cloud)

Для закэшированных страниц:

- нарезка чанков;
- `text-search-doc` / Embeddings API Yandex;
- хранение в PostgreSQL + pgvector или Qdrant;
- retrieval: embedding запроса → top-20 чанков → extract/answer.

Yandex Search остаётся **источником новых URL**, индекс — **глубина по уже виденным страницам**.

### Уровень 4 — краулер (месяцы)

Отдельный worker: очередь URL из search/log, robots.txt, rate limit. Нужен только при масштабе Perplexity-like.

## Рекомендация для Glosix

1. Сейчас: **deep fetch + Redis page_cache** + **query → URL memory** (`page_cache.py`, `query_url_memory.py`).
2. Следующий шаг: **pgvector + Yandex embeddings** для чанков из кэша.
4. Полный краулер — только при >10k DAU.

### Redis на проде

- `maxmemory` + `volatile-lru` — вытесняются ключи с TTL при нехватке RAM.
- Оценка: ~30–80 KB на URL → 10k URL ≈ 0.5–0.8 GB.
