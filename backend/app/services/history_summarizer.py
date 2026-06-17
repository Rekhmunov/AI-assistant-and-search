"""Суммаризация длинной истории диалога через Lite LLM.

Порог: если история > SUMMARIZE_THRESHOLD сообщений —
сжимаем «старые» (все кроме последних KEEP_RECENT) в краткое резюме,
последние KEEP_RECENT передаём целиком.

Резюме кэшируется в Redis: ключ = thread_id + кол-во суммируемых сообщений.
При добавлении новых сообщений кол-во растёт → новый ключ → новая суммаризация.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Если история длиннее этого порога — запускаем суммаризацию
SUMMARIZE_THRESHOLD = 8

# Последние N сообщений всегда передаём целиком (рабочая память)
KEEP_RECENT = 6

# TTL кэша резюме — 24 часа
_SUMMARY_TTL_SEC = 86_400

_SYSTEM = "Ты — помощник, который точно сжимает диалоги в краткие резюме."

_PROMPT_TMPL = """Сожми следующий диалог в краткое резюме на русском (3–8 предложений).
Сохрани: главную тему, что уже было сделано или решено, важные детали \
(технологии, команды, настройки, ошибки, договорённости).
Не добавляй ничего от себя. Только сплошной текст, без списков и заголовков.

Диалог:
{dialogue}"""


def _build_dialogue_text(messages: list[tuple[str, str]], max_chars_per_msg: int = 1500) -> str:
    parts = []
    for role, text in messages:
        label = "Пользователь" if role == "user" else "Ассистент"
        parts.append(f"{label}: {text[:max_chars_per_msg]}")
    return "\n\n".join(parts)


async def summarize_history_if_needed(
    history: list[tuple[str, str]],
    llm_lite,
    redis_client,
    thread_id,
) -> list[tuple[str, str]]:
    """
    Если history <= SUMMARIZE_THRESHOLD — возвращает как есть.
    Иначе суммаризует старые сообщения и возвращает [резюме] + последние KEEP_RECENT.
    """
    if len(history) <= SUMMARIZE_THRESHOLD:
        return history

    old = history[:-KEEP_RECENT]
    recent = history[-KEEP_RECENT:]

    cache_key = f"hist_summary:{thread_id}:{len(old)}"

    # Пробуем кэш
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            summary_msg = ("assistant", f"[Резюме предыдущего диалога]\n{cached}")
            return [summary_msg] + recent
    except Exception:
        pass  # Redis недоступен — продолжаем без кэша

    # Генерируем резюме через Lite LLM
    dialogue = _build_dialogue_text(old)
    messages = [
        {"role": "system", "text": _SYSTEM},
        {"role": "user", "text": _PROMPT_TMPL.format(dialogue=dialogue)},
    ]

    try:
        summary = await llm_lite.complete_text(
            messages,
            model="lite",
            max_tokens=600,
            temperature=0.1,
        )
        summary = (summary or "").strip()
    except Exception as exc:
        logger.warning("history_summarizer: LLM failed, using truncated history: %s", exc)
        # Фоллбэк: отдаём последние SUMMARIZE_THRESHOLD сообщений без суммаризации
        return history[-SUMMARIZE_THRESHOLD:]

    if not summary:
        return history[-SUMMARIZE_THRESHOLD:]

    # Сохраняем в кэш
    try:
        await redis_client.set(cache_key, summary, ex=_SUMMARY_TTL_SEC)
    except Exception:
        pass

    summary_msg = ("assistant", f"[Резюме предыдущего диалога]\n{summary}")
    return [summary_msg] + recent
