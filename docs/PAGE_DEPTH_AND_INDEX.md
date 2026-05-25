# Глубина страниц и накопление индекса

## Текущая модель (v5 + deep pages + Redis cache)

1. Yandex Search — **находит URL** и даёт passage.
2. `fetch_page_full_text` — Redis `page_cache` (gzip) или HTTP:
   - до **48k** символов в кэш, **56 KB** сжатый максимум на ключ;
   - TTL: погода 1ч, ЦБ 30м, новости 6ч, справочники 72ч, остальное 48ч;
   - не кэшируем: PDF, соцсети, login, текст < 400 символов.
3. `enrich_sources_deep` — чанки ~900 символов, топ **4–5** под запрос.
4. `extract` → FactPack → `answer`.

В `debug_trace`: `page_cache: { hits, misses, fetched }`.

Отключить кэш: `PAGE_CACHE_ENABLED=false` в `.env`.

Проверка: `GET /api/health/page-cache`.

## Свой индекс (поэтапно)

### Уровень 0 — только live fetch

Без Redis (если кэш выключен).

### Уровень 1 — кэш URL в Redis (внедрено)

Ключ `pc:v1:{sha256(url)}`, значение gzip(text), TTL по типу домена.

### Уровень 2 — индекс «вопрос → URL»

Таблица `query_url_log(normalized_query, url, score, hit_count)`:

- после каждого удачного ответа сохранять пары query+url с высоким retrieval;
- при похожем запросе — **сначала** подмешивать эти URL в search (bootstrap), потом Yandex Search.

Это не полнотекстовый индекс, а **память сервиса** на ваших пользователях.

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

1. Сейчас: **deep fetch + Redis page_cache** (`page_cache.py`).
2. Следующий шаг: **query → URL memory** в Postgres.
3. Потом: **pgvector + Yandex embeddings** для чанков из кэша.
4. Полный краулер — только при >10k DAU.

### Redis на проде

- `maxmemory` + `volatile-lru` — вытесняются ключи с TTL при нехватке RAM.
- Оценка: ~30–80 KB на URL → 10k URL ≈ 0.5–0.8 GB.
