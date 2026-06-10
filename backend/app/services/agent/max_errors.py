"""Разбор ошибок MAX API для агента и dispatch."""

from __future__ import annotations

import json
import re


def explain_max_send_error(
    error: str | None,
    *,
    chat_id: int | None = None,
    user_id: int | None = None,
) -> str:
    raw = (error or "неизвестная ошибка").strip()
    low = raw.lower()

    if "bot_token not configured" in low:
        return "На сервере не настроен BOT_TOKEN — обратитесь в поддержку Glosix."

    if "no max_user_id or chat_id" in low:
        return "Не указан получатель: нужен chat_id группы или user_id личного чата."

    if chat_id is not None and "max_chat_id missing" in low:
        return f"ID группы MAX не задан. Добавьте бота в группу или укажите chat_id ({chat_id})."

    if "rate_limited" in low or "429" in low:
        return "MAX временно ограничил частоту запросов. Отправка будет повторена автоматически."

    if "attachment.not.ready" in low:
        return "Вложение (картинка) ещё не готово на стороне MAX. Обычно помогает повтор через минуту."

    if "401" in low or "authentication" in low or "unauthorized" in low:
        return "Ошибка авторизации бота в MAX (токен). Проверьте BOT_TOKEN на сервере."

    if "403" in low or "forbidden" in low:
        target = f"группу {chat_id}" if chat_id else "чат"
        return (
            f"MAX отклонил отправку в {target}: у бота нет прав "
            "(возможно, сняли админа или удалили из чата)."
        )

    if "404" in low or "not found" in low:
        target = f"chat_id={chat_id}" if chat_id else "получатель"
        return f"Чат не найден ({target}). Проверьте, что бот добавлен в группу/канал."

    if "400" in low or "invalid" in low:
        return "Некорректный запрос к MAX API. Возможно, слишком длинный текст или неверный chat_id."

    if "503" in low or "service unavailable" in low:
        return "MAX API временно недоступен. Повторим отправку позже."

    # Попытка извлечь message из JSON-ответа MAX
    parsed = _try_parse_json_message(raw)
    if parsed:
        return parsed

    if user_id:
        return f"Не удалось отправить в личку MAX (user_id={user_id}): {raw[:200]}"
    if chat_id:
        return f"Не удалось отправить в группу {chat_id}: {raw[:200]}"
    return f"Ошибка MAX API: {raw[:300]}"


def _try_parse_json_message(raw: str) -> str | None:
    try:
        data = json.loads(raw)
    except ValueError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except ValueError:
            return None
    if not isinstance(data, dict):
        return None
    for key in ("message", "error", "description", "detail"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:400]
    return None
