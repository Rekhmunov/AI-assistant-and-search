# GigaChat API

## GIGACHAT_CREDENTIALS

Это **ключ авторизации** из личного кабинета [developers.sber.ru](https://developers.sber.ru/) → проект GigaChat → блок **«Авторизационные данные»**.

- Формат: одна строка **Base64** (Client ID:Client Secret в Base64), без префикса `Basic `.
- В `.env`: `GIGACHAT_CREDENTIALS=<вставить ключ целиком>`
- Scope для личного API: `GIGACHAT_API_PERS`

## SSL: CERTIFICATE_VERIFY_FAILED

GigaChat (`*.sberbank.ru`, `ngw.devices.sberbank.ru`) подписан цепочкой **НУЦ Минцифры**. В Docker/Python по умолчанию используется `certifi`, где этого корня нет — отсюда `self-signed certificate in certificate chain`.

### Вариант A (рекомендуется для prod)

1. Скачайте **Russian Trusted Root CA** с [gosuslugi.ru/crt](https://www.gosuslugi.ru/crt) или:

   ```bash
   curl -fsSL "https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt" \
     -o /opt/aisearch/certs/russian_trusted_root_ca.pem
   ```

2. Примонтируйте каталог в `backend` (если ещё не смонтирован) и в `.env`:

   ```env
   GIGACHAT_CA_BUNDLE_FILE=/opt/aisearch/certs/russian_trusted_root_ca.pem
   GIGACHAT_VERIFY_SSL_CERTS=true
   ```

3. Пересоздайте контейнеры:

   ```bash
   docker compose -f docker-compose.prod.yml up -d --force-recreate backend worker
   ```

Путь `GIGACHAT_CA_BUNDLE_FILE` должен быть **внутри контейнера** (тот же файл, что видит процесс backend).

### Вариант B (быстро, менее безопасно)

Только если нельзя смонтировать сертификат:

```env
GIGACHAT_VERIFY_SSL_CERTS=false
```

После смены `.env` — обязательно `force-recreate` backend и worker.

## Проверка

- Админка → «Проверить GigaChat»
- Или: `curl -s https://glosix.ru/api/health/gigachat` (с вашим хостом)
