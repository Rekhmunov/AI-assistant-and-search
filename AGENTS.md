# Instructions for AI agents

## Git workflow

- **Work only on `main`.** Do not create feature branches (`cursor/*` or otherwise).
- Commit and push directly to `origin/main`.
- Do not open separate PRs unless the user explicitly asks for a PR.

## Production deploy

- Server path: `/opt/aisearch`
- Update: `bash scripts/update.sh` (from repo root)
- Secrets: `.env` only (never commit). `nginx/nginx.prod.conf` is local/generated — not tracked in git.

## MAX API: проверка админа в группе

По [документации MAX](https://dev.max.ru/docs-api/methods/GET/chats/-chatId-/members) бот **может сам проверить**, является ли он администратором группы или канала:

1. `GET /me` — `user_id` бота.
2. `GET /chats/{chatId}/members?user_ids={bot_user_id}` — в объекте `ChatMember` поля `is_admin`, `is_owner`, `permissions`.

Ограничения:

- Метод `/chats/{chatId}/members` доступен, если бот **уже в чате**; для проверки прав на members бот должен быть **админом** (иначе API вернёт ошибку — трактуем как «проверить не удалось», спрашиваем пользователя).
- Для **исходящих** постов в группу (news_digest, group_reminder) админ **не обязателен**; для модерации, чтения всех сообщений и `group_message_log` — нужен.
- Реализация: `MaxBotService.check_bot_is_group_admin()`, вызов при онбординге в `enrich_group_admin_status()`.
