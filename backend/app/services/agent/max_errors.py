"""Разбор ошибок MAX API и ошибок безопасности агента."""

from __future__ import annotations

import json
import re

# Коды ошибок безопасности агента → человекочитаемые объяснения
_SECURITY_ERROR_MESSAGES: dict[str, str] = {
    "chat_id_forbidden": (
        "Этот чат не привязан к агенту. Сначала добавьте бота в группу или укажите "
        "корректный chat_id через ссылку на канал/группу."
    ),
    "chat_id_required": (
        "Не указан chat_id группы или канала. Пришлите ссылку на группу (max.ru/-ID) "
        "или ID чата."
    ),
    "chat_id_or_user_id_required": (
        "Не указан получатель: нужен chat_id для группы/канала или user_id для личного сообщения."
    ),
    "user_id_forbidden": (
        "Личные сообщения можно отправлять только владельцу агента. "
        "Отправка другим пользователям не разрешена."
    ),
    "test_send_not_allowed": (
        "Отправка тестовых сообщений требует явного разрешения. "
        "Напишите «проверь группу» или «отправь тестовое сообщение», чтобы разрешить."
    ),
    "file_send_not_allowed": (
        "Отправка файлов и сообщений требует явного разрешения в этом контексте."
    ),
    "message_too_long": (
        f"Текст сообщения слишком длинный (MAX ограничивает до 4000 символов). "
        "Сократите текст или разбейте на несколько сообщений."
    ),
    "empty_message": "Текст сообщения не может быть пустым.",
    "invalid_message_text": (
        "Текст сообщения некорректен: пустой или превышает 4000 символов."
    ),
    "invalid_file_instruction": (
        "Инструкция для генерации файла пустая или слишком длинная (максимум 2000 символов)."
    ),
    "invalid_file_format": (
        "Неподдерживаемый формат файла. Доступны: docx (Word), pdf, xlsx (Excel), image (картинка)."
    ),
    "invalid_link": "Неверный формат ссылки на канал или группу MAX.",
    "invalid_search_query": "Пустой или слишком длинный поисковый запрос.",
    "invalid_memory_note": "Заметка для памяти агента пустая или слишком длинная.",
    "invalid_record_data": "Данные для записи должны быть объектом (словарём).",
    "tool_not_allowed": "Этот инструмент недоступен агенту.",
    "unknown_tool": "Неизвестный инструмент. Используйте только инструменты из списка.",
}


def explain_security_error(code: str) -> str:
    """Переводит код AgentSecurityError в человекочитаемое объяснение."""
    # Обрезаем суффикс после двоеточия (например tool_not_allowed:web_hook)
    base = code.split(":")[0].strip()
    return _SECURITY_ERROR_MESSAGES.get(base) or f"Ошибка безопасности агента: {code}"


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
