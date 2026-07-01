"""Исполнитель агента «Постинг» — генерация, рефлексия, публикация."""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)

# Хранение истории и черновиков прямо в agent.config
_MAX_HISTORY = 30
_DRAFT_PENDING_KEY = "poster_pending_draft"


# ─────────────────────────────────────────────────────────────────────────────
# Конфиг агента
# ─────────────────────────────────────────────────────────────────────────────

def _get_cfg(agent: AgentInstance) -> dict:
    return dict(agent.config or {})


def _save_cfg(agent: AgentInstance, cfg: dict) -> None:
    from sqlalchemy.orm.attributes import flag_modified
    agent.config = cfg
    flag_modified(agent, "config")


def get_poster_channel_id(agent: AgentInstance) -> int | None:
    cfg = _get_cfg(agent)
    raw = cfg.get("poster_channel_id") or cfg.get("max_chat_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def get_approval_mode(agent: AgentInstance) -> str:
    """'manual' | 'auto'"""
    cfg = _get_cfg(agent)
    # Structured config takes priority over text-based instructions
    if "poster_approval" in cfg:
        return "manual" if cfg["poster_approval"] else "auto"
    instr = str(cfg.get("support_instructions") or "").lower()
    if "автоматически" in instr or "без согласования" in instr:
        return "auto"
    return "manual"


def get_reflection_enabled(agent: AgentInstance) -> bool:
    cfg = _get_cfg(agent)
    if "poster_reflection" in cfg:
        return bool(cfg["poster_reflection"])
    instr = str(cfg.get("support_instructions") or "").lower()
    return "рефлексия: нет" not in instr


_DAY_LABELS_RU = {
    "mon": "Пн", "tue": "Вт", "wed": "Ср",
    "thu": "Чт", "fri": "Пт", "sat": "Сб", "sun": "Вс",
}


def get_poster_schedule(agent: AgentInstance) -> list[dict]:
    """Return list of {day, time} slots. Supports both poster_schedule and legacy poster_days/poster_time."""
    cfg = _get_cfg(agent)
    schedule = cfg.get("poster_schedule")
    if isinstance(schedule, list) and schedule:
        return [s for s in schedule if isinstance(s, dict) and s.get("day") and s.get("time")]
    # Legacy fallback
    days = cfg.get("poster_days", [])
    time = cfg.get("poster_time", "10:00")
    if isinstance(days, list) and days:
        return [{"day": d, "time": time} for d in days]
    return []


# Maps use RUSSIAN labels — matching what ChipsField sends from the frontend.
# Keys are the exact chip display values; values are expanded LLM instructions.
_POST_FORMAT_MAP: dict[str, str] = {
    "Новость + вывод":  "Структура: [Хук-заголовок] → [Факт + неочевидный вывод] → [Значение для читателя]",
    "Топ-5 список":     "Структура: [Цепляющий хук] → [5 пронумерованных пунктов] → [Краткий итог]",
    "How-to":           "Структура: [Проблема] → [Шаги 1–3 кратко] → [Результат]",
    "Вопрос аудитории": "Структура: [Провокационный вопрос] → [2–3 предложения контекста] → [Приглашение ответить]",
    "Кейс":             "Структура: [Герой/компания] → [Проблема] → [Решение] → [Измеримый результат]",
    "Мнение":           "Структура: [Смелое утверждение] → [3 аргумента] → [Вывод]",
}

_HOOK_STYLE_MAP: dict[str, str] = {
    "Провокация":          "Первая строка — провокационное или контринтуитивное утверждение",
    "Вопрос":              "Первая строка — вопрос, который задевает читателя и провоцирует дочитать до конца",
    "Неожиданная цифра":   "Первая строка — неожиданная цифра или конкретный факт (не общеизвестный)",
    "Начало истории":      "Первая строка — начало короткой истории (1–2 предложения, реальный сценарий)",
}

_CTA_TYPE_MAP: dict[str, str] = {
    "Вопрос для комментариев": "CTA: в конце задай открытый вопрос, приглашающий оставить комментарий",
    "Сохранить пост":          "CTA: в конце попроси сохранить пост, объяснив чем он полезен",
    "Переслать коллегам":      "CTA: в конце попроси переслать коллегам, которым это актуально",
    "Подписаться":             "CTA: в конце мягко предложи подписаться, чтобы не пропустить следующее",
    "Ссылка в описании":       "CTA: в конце направь по ссылке (упомяни что ссылка в описании канала)",
}

_DEFAULT_STOPWORDS = (
    "на сегодняшний день, в рамках, осуществляется, осуществить, данный, "
    "является, следует отметить, в настоящее время, хочется сказать, "
    "стоит отметить, не могу не, в заключение, подводя итог, резюмируя"
)


def _build_style_from_config(agent: AgentInstance) -> str:
    """Build human-readable style instructions from structured poster config keys."""
    cfg = _get_cfg(agent)
    parts = []
    topic_list = _get_topic_list(agent)
    if topic_list:
        parts.append(f"Темы: {'; '.join(t['text'] for t in topic_list)}")
    mode_labels = {"random": "случайный", "no_repeat": "случайный без повторов",
                   "sequential": "по очереди", "priority": "приоритетный"}
    mode = cfg.get("poster_topic_mode", "no_repeat")
    parts.append(f"Порядок тем: {mode_labels.get(mode, mode)}")
    tone = cfg.get("poster_tone", "")
    tone_map = {
        "official": "официальный", "informal": "неформальный",
        "expert": "экспертный", "inspiring": "вдохновляющий",
        "humorous": "лёгкий с юмором", "provocative": "провокационный",
    }
    if tone:
        parts.append(f"Тон: {tone_map.get(tone, tone)}")
    emoji = cfg.get("poster_emoji", True)
    parts.append(f"Эмодзи: {'да' if emoji else 'нет'}")
    length = cfg.get("poster_length", "medium")
    length_map = {"short": "короткий (~500 зн.)", "medium": "средний (~1000 зн.)", "long": "длинный (~2000 зн.)"}
    parts.append(f"Длина: {length_map.get(length, length)}")

    def _expand_tokens(raw: str, key_map: dict[str, str], prefix: str) -> list[str]:
        """Split comma-separated multi-select value, expand each token through the map."""
        result = []
        for token in (t.strip() for t in raw.split(",") if t.strip()):
            if token in ("auto", "none"):
                continue
            mapped = key_map.get(token)
            result.append(mapped if mapped else f"{prefix}: {token}")
        return result

    # Post format — supports multiple comma-separated values
    post_format = str(cfg.get("poster_format") or "auto").strip()
    if post_format and post_format != "auto":
        fmt_parts = _expand_tokens(post_format, _POST_FORMAT_MAP, "СТРУКТУРА ПОСТА")
        if len(fmt_parts) == 1:
            parts.append(fmt_parts[0])
        elif len(fmt_parts) > 1:
            parts.append("ФОРМАТЫ (чередуй или сочетай):\n" + "\n".join(f"- {p}" for p in fmt_parts))

    # Hook style — supports multiple comma-separated values
    hook = str(cfg.get("poster_hook") or "auto").strip()
    if hook and hook != "auto":
        hook_parts = _expand_tokens(hook, _HOOK_STYLE_MAP, "ПЕРВАЯ СТРОКА")
        if len(hook_parts) == 1:
            parts.append(hook_parts[0])
        elif len(hook_parts) > 1:
            parts.append("ПЕРВАЯ СТРОКА (выбери один из стилей или сочетай):\n" + "\n".join(f"- {p}" for p in hook_parts))

    # Target audience
    audience = str(cfg.get("poster_audience") or "").strip()
    if audience:
        parts.append(f"Целевая аудитория: {audience}")

    # CTA — supports multiple comma-separated values
    cta_type = str(cfg.get("poster_cta_type") or "none").strip()
    if cta_type and cta_type != "none":
        cta_parts = _expand_tokens(cta_type, _CTA_TYPE_MAP, "CTA")
        if len(cta_parts) == 1:
            parts.append(cta_parts[0])
        elif len(cta_parts) > 1:
            parts.append("CTA (выбери один или чередуй между постами):\n" + "\n".join(f"- {p}" for p in cta_parts))
    else:
        parts.append("CTA: нет")

    # Stop words always applied — no UI toggle needed
    parts.append(f"ЗАПРЕЩЁННЫЕ СЛОВА И КЛИШЕ: {_DEFAULT_STOPWORDS}. Никогда не используй их.")

    media = cfg.get("poster_media", "none")
    media_map = {"none": "без изображений", "manual": "изображение вручную", "ai": "генерация ИИ"}
    parts.append(f"Медиа: {media_map.get(media, media)}")
    channel_id = cfg.get("poster_channel_id") or cfg.get("max_chat_id")
    if channel_id:
        parts.append(f"Канал: {channel_id}")
    schedule = get_poster_schedule(agent)
    if schedule:
        slots_str = ", ".join(f"{_DAY_LABELS_RU.get(s['day'], s['day'])} в {s['time']}" for s in schedule)
        parts.append(f"Расписание: {slots_str}")
    else:
        parts.append("Расписание: ручной режим (по запросу)")
    return "\n".join(parts)


def _topic_text(topic) -> str:
    """Extract plain topic string from str | dict {text, search}."""
    if isinstance(topic, dict):
        return str(topic.get("text") or "")
    return str(topic or "")


# Phrases that indicate the LLM leaked its reasoning/thinking instead of post text
_REASONING_LEAK_PATTERNS = [
    r"^мы должны",
    r"^нужно проверить",
    r"^давайте проверим",
    r"^сначала проверим",
    r"^анализируем",
    r"^посчитаем",
    r"^итак,\s*(создадим|напишем|сформируем|улучшим)",
    r"^в данном случае",
    r"^(черновик|текст)[:\s]",
    r"^требования[:\s]",
    r"^\d+\.\s*(соответствует|проверим|нужно)",
]

_THINKING_TAG_RE = re.compile(r"<thinking>.*?</thinking>", re.DOTALL | re.IGNORECASE)
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _clean_llm_post_output(text: str | None, *, fallback: str = "") -> str:
    """
    Sanitize LLM output for use as a published post:
    1. Strip <thinking>/<think> XML tags (DeepSeek R1 / Claude CoT)
    2. Detect if output is reasoning/analysis rather than a post → use fallback
    3. Strip system-level artifacts if the post otherwise looks fine
    """
    if not text:
        return fallback

    cleaned = _THINKING_TAG_RE.sub("", text)
    cleaned = _THINK_TAG_RE.sub("", cleaned)
    cleaned = cleaned.strip()

    if not cleaned:
        return fallback

    # Detect reasoning leak: if the output starts with typical chain-of-thought phrases
    first_line = cleaned.split("\n")[0].strip().lower()
    for pattern in _REASONING_LEAK_PATTERNS:
        if re.match(pattern, first_line, re.IGNORECASE):
            logger.warning("POSTER_REFLECTION: reasoning leak detected (starts with %r) — using original draft",
                           first_line[:60])
            return fallback

    # If the output is very long compared to the original draft and the draft is reasonable,
    # it may be that the model added a lot of reasoning. Use heuristic: if >3× draft length → fallback
    if fallback and len(cleaned) > len(fallback) * 3:
        logger.warning("POSTER_REFLECTION: output %d chars >> draft %d chars → fallback",
                       len(cleaned), len(fallback))
        return fallback

    return cleaned


_POSTER_STRUCTURED_KEYS = frozenset({
    "poster_topics", "poster_topic_list", "poster_tone", "poster_length",
    "poster_format", "poster_hook", "poster_audience", "poster_cta_type",
})


def _parse_style_instructions(agent: AgentInstance) -> str:
    cfg = _get_cfg(agent)
    # Use structured config if ANY poster content key is present
    if any(cfg.get(k) for k in _POSTER_STRUCTURED_KEYS):
        return _build_style_from_config(agent)
    return str(cfg.get("support_instructions") or "")


def _get_topic_list(agent: AgentInstance) -> list[dict]:
    """Return list of topics as dicts {text, search}.
    Supports new {text, search} format, plain string list, and legacy string."""
    cfg = _get_cfg(agent)

    topic_list = cfg.get("poster_topic_list")
    if isinstance(topic_list, list) and topic_list:
        result = []
        for t in topic_list:
            if isinstance(t, dict):
                text = str(t.get("text") or "").strip()
                if text:
                    result.append({"text": text, "search": bool(t.get("search", False))})
            elif str(t).strip():
                result.append({"text": str(t).strip(), "search": False})
        if result:
            return result

    # Legacy: semicolon-separated string
    topics_raw = cfg.get("poster_topics", "")
    if not topics_raw:
        instr = str(cfg.get("support_instructions") or "")
        m = re.search(r"темы:\s*(.+?)(?:\.|$)", instr, re.IGNORECASE)
        topics_raw = m.group(1) if m else ""

    if topics_raw:
        return [{"text": t.strip(), "search": False}
                for t in re.split(r"[;,\n]", topics_raw) if t.strip()]
    return []


def _pick_next_topic(agent: AgentInstance) -> dict:
    """
    Выбирает следующую тему согласно настроенному режиму ротации.
    Возвращает dict {text: str, search: bool}.

    Режимы (poster_topic_mode):
      random      — полностью случайный
      no_repeat   — случайный, но не повторяет тему два раза подряд (default)
      sequential  — строго по очереди 1→2→3→1→...
      priority    — первые темы появляются чаще (убывающий вес)
    """
    import random as _random

    cfg = _get_cfg(agent)
    topics = _get_topic_list(agent)

    if not topics:
        return {"text": "общая тема канала", "search": False}
    if len(topics) == 1:
        return topics[0]

    mode = cfg.get("poster_topic_mode", "no_repeat")
    last_idx = int(cfg.get("poster_last_topic_idx", -1))

    if mode == "random":
        idx = _random.randrange(len(topics))
    elif mode == "sequential":
        idx = (last_idx + 1) % len(topics)
    elif mode == "priority":
        n = len(topics)
        weights = [n - i for i in range(n)]
        idx = _random.choices(range(n), weights=weights, k=1)[0]
    else:  # "no_repeat"
        candidates = [i for i in range(len(topics)) if i != last_idx]
        idx = _random.choice(candidates) if candidates else _random.randrange(len(topics))

    cfg["poster_last_topic_idx"] = idx
    _save_cfg(agent, cfg)
    return topics[idx]


# ─────────────────────────────────────────────────────────────────────────────
# История постов
# ─────────────────────────────────────────────────────────────────────────────

def save_post_to_history(
    agent: AgentInstance,
    *,
    post_id: str,
    topic: str,
    text: str,
    status: str,  # "draft" | "published" | "rejected"
    channel_id: int | None = None,
) -> None:
    cfg = _get_cfg(agent)
    history: list[dict] = cfg.get("poster_history", [])
    history.append({
        "id": post_id,
        "topic": topic,
        "text": text,
        "status": status,
        "channel_id": channel_id,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    cfg["poster_history"] = history[-_MAX_HISTORY:]
    _save_cfg(agent, cfg)


def get_post_history(agent: AgentInstance) -> list[dict]:
    cfg = _get_cfg(agent)
    return list(cfg.get("poster_history", []))


def delete_post_from_history(agent: AgentInstance, post_id: str) -> None:
    """Remove a single post record from history by id."""
    cfg = _get_cfg(agent)
    history = [r for r in cfg.get("poster_history", []) if r.get("id") != post_id]
    cfg["poster_history"] = history
    _save_cfg(agent, cfg)


def clear_post_history(agent: AgentInstance) -> None:
    """Remove all post history records."""
    cfg = _get_cfg(agent)
    cfg["poster_history"] = []
    _save_cfg(agent, cfg)


def update_post_status(agent: AgentInstance, post_id: str, status: str) -> None:
    cfg = _get_cfg(agent)
    history: list[dict] = cfg.get("poster_history", [])
    for record in history:
        if record.get("id") == post_id:
            record["status"] = status
            break
    cfg["poster_history"] = history
    _save_cfg(agent, cfg)


# ─────────────────────────────────────────────────────────────────────────────
# Черновик (pending draft)
# ─────────────────────────────────────────────────────────────────────────────

MAX_DRAFT_IMAGES = 4  # maximum photos per post


def save_pending_draft(
    agent: AgentInstance,
    *,
    post_id: str,
    topic: str,
    text: str,
    draft_message_id: str | None = None,
    image_file_ids: list[str] | None = None,
) -> None:
    cfg = _get_cfg(agent)
    draft: dict = {
        "post_id": post_id,
        "topic": topic,
        "text": text,
        "draft_message_id": draft_message_id,
        "awaiting_edit": False,
    }
    if image_file_ids is not None:
        draft["image_file_ids"] = image_file_ids[:MAX_DRAFT_IMAGES]
    elif _DRAFT_PENDING_KEY in cfg:
        # Preserve existing image_file_ids when updating other fields
        draft["image_file_ids"] = cfg[_DRAFT_PENDING_KEY].get("image_file_ids", [])
    cfg[_DRAFT_PENDING_KEY] = draft
    _save_cfg(agent, cfg)


def get_draft_image_file_ids(agent: AgentInstance) -> list[str]:
    """Return list of image file IDs stored in the pending draft."""
    draft = get_pending_draft(agent)
    if not draft:
        return []
    return list(draft.get("image_file_ids") or [])


def set_draft_image_file_ids(agent: AgentInstance, file_ids: list[str]) -> None:
    """Update image_file_ids in pending draft without touching other fields.
    Safety: if the draft has no post_id (was cleared by a concurrent regen),
    we do NOT overwrite it to avoid corrupting the new draft's state.
    """
    cfg = _get_cfg(agent)
    draft = cfg.get(_DRAFT_PENDING_KEY, {})
    if not draft.get("post_id"):
        # Draft was cleared concurrently — do not recreate a broken state
        logger.warning("set_draft_image_file_ids: draft has no post_id, skipping (concurrent regen?)")
        return
    draft["image_file_ids"] = file_ids[:MAX_DRAFT_IMAGES]
    cfg[_DRAFT_PENDING_KEY] = draft
    _save_cfg(agent, cfg)


def get_pending_draft(agent: AgentInstance) -> dict | None:
    cfg = _get_cfg(agent)
    return cfg.get(_DRAFT_PENDING_KEY)


def clear_pending_draft(agent: AgentInstance) -> None:
    cfg = _get_cfg(agent)
    cfg.pop(_DRAFT_PENDING_KEY, None)
    _save_cfg(agent, cfg)


def set_awaiting_edit(agent: AgentInstance, awaiting: bool) -> None:
    cfg = _get_cfg(agent)
    draft = cfg.get(_DRAFT_PENDING_KEY, {})
    draft["awaiting_edit"] = awaiting
    cfg[_DRAFT_PENDING_KEY] = draft
    _save_cfg(agent, cfg)


# ─────────────────────────────────────────────────────────────────────────────
# Генерация поста
# ─────────────────────────────────────────────────────────────────────────────

async def generate_poster_image(
    agent: AgentInstance,
    topic: str,
    post_text: str,
    *,
    db,
    redis_client,
) -> bytes | None:
    """
    Генерирует изображение для поста если poster_media='ai'.
    Использует провайдер генерации картинок из настроек админки.
    Возвращает байты изображения или None.
    """
    cfg = _get_cfg(agent)
    media_mode = cfg.get("poster_media", "none")
    logger.warning("POSTER_IMG agent=%s poster_media=%s topic=%s", agent.id, media_mode, topic[:50])
    if media_mode != "ai":
        logger.warning("POSTER_IMG skipped: poster_media=%s (not 'ai')", media_mode)
        return None
    try:
        from app.services.image_gen_service import generate_image, resolve_image_gen_provider_id
        from app.services.image_gen_service import ImageGenerationError
        provider_id = await resolve_image_gen_provider_id(db, redis_client)
        logger.warning("POSTER_IMG: provider=%s prompt_start=%r", provider_id, topic[:60])
        # Тема может содержать структурные инструкции для текстового LLM
        # (например «Структура: описание блюда...»). Для модели картинок
        # берём только название темы — до первого «.» или «:».
        # Текст поста (первые 200 символов) даёт визуальный контекст.
        _clean_topic = topic.split(".")[0].split(":")[0].strip()[:100]
        _post_preview = post_text[:200].strip() if post_text else ""
        _content = f"{_clean_topic}. {_post_preview}" if _post_preview else _clean_topic
        img_prompt = f"Нарисуй картинку к посту: {_content}"
        image_bytes, _ = await generate_image(img_prompt, provider_id)
        logger.warning("POSTER_IMG success: %d bytes provider=%s", len(image_bytes), provider_id)
        return image_bytes
    except ImageGenerationError as exc:
        logger.warning("POSTER_IMG ImageGenerationError code=%s msg=%s", exc.code if hasattr(exc, 'code') else '?', exc)
        return None
    except Exception as exc:
        logger.warning("POSTER_IMG FAILED provider=%s exc_type=%s msg=%s", locals().get('provider_id', '?'), type(exc).__name__, exc)
        return None


async def generate_post(
    agent: AgentInstance,
    topic,  # str | dict {text, search}
    llm,
    *,
    db=None,
    redis_client=None,
) -> str:
    """
    Генерирует пост. Если у темы установлен флаг search=True, сначала
    выполняется поиск Яндекс, и результаты передаются в LLM как контекст.
    Рефлексия применяется если включена в настройках.

    topic может быть строкой (обратная совместимость) или dict {text, search}.
    """
    from app.services.agent.templates.poster import (
        POSTER_GENERATION_PROMPT,
        POSTER_GENERATION_PROMPT_WITH_SEARCH,
        POSTER_REFLECTION_PROMPT,
    )

    # Normalize topic
    if isinstance(topic, dict):
        topic_text = str(topic.get("text") or "")
        topic_search = bool(topic.get("search", False))
    else:
        topic_text = str(topic)
        topic_search = False

    style = _parse_style_instructions(agent)
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")

    # Формируем блок недавних постов чтобы LLM не повторял темы/примеры
    recent_history = get_post_history(agent)
    published = [r for r in recent_history if r.get("status") == "published"][-5:]
    if published:
        lines = [f"- {r.get('topic', '?')}: {str(r.get('text', ''))[:80]}..." for r in published]
        recent_posts_block = "НЕДАВНИЕ ПОСТЫ (не повторяй темы и примеры):\n" + "\n".join(lines) + "\n\n"
    else:
        recent_posts_block = ""

    # Шаг 1 (опциональный): Поиск актуальных данных Яндекс
    search_context = ""
    if topic_search and db is not None and redis_client is not None:
        try:
            from app.services.yandex_search import YandexSearchService
            _svc = YandexSearchService()
            results = await _svc.search(topic_text, limit=5)
            if results:
                lines = []
                for r in results[:5]:
                    # SearchSource is a dataclass with .title, .snippet, .url
                    title = r.title or ""
                    snippet = r.snippet or ""
                    url = r.url or ""
                    lines.append(f"• {title}\n  {snippet[:300]}\n  {url}")
                search_context = "\n\n".join(lines)
                logger.info("POSTER_SEARCH: found %d results for topic=%s", len(results), topic_text[:50])
        except Exception as exc:
            logger.warning("POSTER_SEARCH failed (topic=%s): %s", topic_text[:50], exc)

    # Шаг 2: Генерация черновика
    if search_context:
        prompt_text = POSTER_GENERATION_PROMPT_WITH_SEARCH.format(
            topic=topic_text,
            style_instructions=style[:1500],
            current_date=today,
            search_results=search_context[:3000],
            recent_posts_block=recent_posts_block,
        )
    else:
        prompt_text = POSTER_GENERATION_PROMPT.format(
            topic=topic_text,
            style_instructions=style[:1500],
            current_date=today,
            recent_posts_block=recent_posts_block,
        )

    raw_draft = await llm.complete_text(
        [{"role": "user", "text": prompt_text}],
        model="pro", max_tokens=2000, temperature=0.7,
    )
    draft = _clean_llm_post_output(raw_draft)

    if not draft:
        return f"Пост на тему: {topic_text}\n\n[Не удалось сгенерировать контент]"

    # Шаг 3: Рефлексия (если включена)
    if get_reflection_enabled(agent):
        try:
            refl_messages = [
                {"role": "user", "text": POSTER_REFLECTION_PROMPT.format(
                    topic=topic_text,
                    style_instructions=style[:1500],
                    draft=draft,
                )}
            ]
            refined = await llm.complete_text(refl_messages, model="pro", max_tokens=2000, temperature=0.3)
            refined = _clean_llm_post_output(refined, fallback=draft)
            if refined:
                draft = refined
        except Exception as exc:
            logger.warning("Poster reflection failed: %s", exc)

    return draft


# ─────────────────────────────────────────────────────────────────────────────
# Отправка черновика на согласование
# ─────────────────────────────────────────────────────────────────────────────

def get_approval_destination(agent: AgentInstance) -> tuple[int | None, int | None]:
    """
    Returns (chat_id, user_id) for sending approval draft.
    Prefers group chat (max_chat_id), falls back to DM with owner (max_user_id).
    Exactly one of them will be non-None.
    """
    cfg = _get_cfg(agent)
    chat_id = agent.max_chat_id or cfg.get("registered_group_chat_id")
    if chat_id:
        return int(chat_id), None
    user_id = agent.max_user_id
    if user_id:
        return None, int(user_id)
    return None, None


async def _build_draft_attachments(
    bot: MaxBotService,
    agent: AgentInstance,
    post_id: str,
    image_bytes: bytes | None = None,
    image_bytes_list: list[bytes] | None = None,
) -> list:
    """Build list of attachments: optional image(s) + keyboard buttons."""
    attachments = []

    all_images: list[bytes] = []
    if image_bytes_list:
        all_images = image_bytes_list[:MAX_DRAFT_IMAGES]
    elif image_bytes:
        all_images = [image_bytes]

    for img in all_images:
        try:
            token = await _upload_image_to_max(bot, img)
            if token:
                attachments.append({"type": "image", "payload": {"token": token}})
            else:
                logger.warning("send_draft_for_approval: image upload returned empty token")
        except Exception as exc:
            logger.warning("send_draft_for_approval: image upload failed: %s", exc)

    keyboard = bot.make_keyboard_attachment([
        [
            {"type": "callback", "text": "✅ Опубликовать", "payload": f"poster:approve:{agent.id}:{post_id}"},
            {"type": "callback", "text": "🔄 Перегенерировать", "payload": f"poster:regen:{agent.id}:{post_id}"},
        ],
        [
            {"type": "callback", "text": "✏️ Редактировать", "payload": f"poster:edit:{agent.id}:{post_id}"},
            {"type": "callback", "text": "❌ Отклонить", "payload": f"poster:reject:{agent.id}:{post_id}"},
        ],
    ])
    attachments.append(keyboard)
    return attachments


async def send_draft_for_approval(
    agent: AgentInstance,
    db: AsyncSession,
    bot: MaxBotService,
    *,
    approval_chat_id: int | None = None,
    post_id: str,
    topic: str,
    text: str,
    image_bytes: bytes | None = None,
    image_bytes_list: list[bytes] | None = None,
) -> str | None:
    """
    Отправляет черновик с кнопками согласования (опционально с изображением).
    Если approval_chat_id не указан — определяет назначение из конфига агента.
    Возвращает message_id отправленного сообщения.
    """
    header = f"📝 **Черновик поста** — тема: _{topic}_\n\n"
    photo_hint = "\n\n📎 _Отправьте фото в этот чат, чтобы добавить его к посту._"
    full_text = header + text + photo_hint
    attachments = await _build_draft_attachments(bot, agent, post_id, image_bytes, image_bytes_list)

    if approval_chat_id:
        dest_chat_id, dest_user_id = approval_chat_id, None
    else:
        dest_chat_id, dest_user_id = get_approval_destination(agent)

    if dest_chat_id:
        result = await bot.send_message(
            None, full_text, attachments=attachments,
            chat_id=dest_chat_id, notify=True,
        )
    elif dest_user_id:
        result = await bot.send_message(
            dest_user_id, full_text, attachments=attachments,
        )
    else:
        logger.warning("send_draft_for_approval: no destination for agent=%s", agent.id)
        return None

    return result.message_id if result.ok else None


async def edit_draft_message(
    bot: MaxBotService,
    agent: AgentInstance,
    *,
    draft_message_id: str,
    post_id: str,
    topic: str,
    text: str,
    image_bytes: bytes | None = None,
    image_bytes_list: list[bytes] | None = None,
) -> bool:
    """Edit existing DM/group draft message with new content."""
    header = f"📝 **Черновик поста** — тема: _{topic}_\n\n"
    full_text = header + text
    attachments = await _build_draft_attachments(bot, agent, post_id, image_bytes, image_bytes_list)
    return await bot.edit_message(draft_message_id, full_text, attachments=attachments)


async def mark_draft_message_done(
    bot: MaxBotService,
    *,
    draft_message_id: str,
    status_text: str,
) -> None:
    """Replace draft message with a simple status (no buttons)."""
    try:
        await bot.edit_message(draft_message_id, status_text)
    except Exception as exc:
        logger.warning("mark_draft_message_done failed: %s", exc)


async def send_dm_notification(
    agent: AgentInstance,
    bot: MaxBotService,
    *,
    owner_max_user_id: int,
    approval_chat_id: int,
) -> None:
    """Уведомление в DM владельца."""
    from app.core.config import get_settings
    settings = get_settings()
    bot_base = (settings.max_bot_url or "").strip().rstrip("/").split("?")[0]
    link = f"{bot_base}?startapp=chat_{approval_chat_id}" if bot_base else ""

    text = (
        "📋 Новый черновик поста готов к согласованию.\n"
        "Откройте чат агента для просмотра и подтверждения."
    )
    await bot.send_message(owner_max_user_id, text)


# ─────────────────────────────────────────────────────────────────────────────
# Публикация в канал
# ─────────────────────────────────────────────────────────────────────────────

async def _upload_image_to_max(bot: MaxBotService, image_bytes: bytes) -> str | None:
    """Upload a single image to MAX CDN, return attachment token."""
    from app.services.image_bytes import detect_image_mime
    mime = detect_image_mime(image_bytes)
    filename = "post_image.png" if mime == "image/png" else "post_image.jpg"
    logger.warning("POSTER_UPLOAD %d bytes as %s", len(image_bytes), filename)
    token = await bot.upload_media(image_bytes, filename, "image")
    logger.warning("POSTER_UPLOAD token=%s", bool(token))
    return token


async def publish_to_channel(
    bot: MaxBotService,
    *,
    channel_id: int,
    text: str,
    image_bytes: bytes | None = None,
    image_bytes_list: list[bytes] | None = None,
) -> bool:
    """
    Публикует пост в канал.
    image_bytes — одно изображение (обратная совместимость).
    image_bytes_list — список изображений до MAX_DRAFT_IMAGES.
    """
    attachments = []

    all_images: list[bytes] = []
    if image_bytes_list:
        all_images = image_bytes_list[:MAX_DRAFT_IMAGES]
    elif image_bytes:
        all_images = [image_bytes]

    for img in all_images:
        try:
            token = await _upload_image_to_max(bot, img)
            if token:
                attachments.append({"type": "image", "payload": {"token": token}})
            else:
                logger.warning("POSTER_PUBLISH image upload returned empty token")
        except Exception as exc:
            logger.warning("POSTER_PUBLISH image upload failed: %s", exc)

    result = await bot.send_message(
        None, text, attachments=attachments or None,
        chat_id=channel_id, notify=True,
    )
    logger.warning("POSTER_PUBLISH ok=%s images=%d", result.ok, len(attachments))
    return result.ok


# ─────────────────────────────────────────────────────────────────────────────
# Форматирование истории
# ─────────────────────────────────────────────────────────────────────────────

def format_post_history(history: list[dict]) -> str:
    if not history:
        return "История постов пуста."

    status_labels = {
        "published": "✅ опубликован",
        "rejected": "❌ отклонён",
        "draft": "📝 черновик",
    }
    lines = ["**Последние посты:**\n"]
    for record in reversed(history[-10:]):
        at = record.get("at", "")[:10]
        topic = record.get("topic", "—")
        status = status_labels.get(record.get("status", ""), record.get("status", ""))
        lines.append(f"• {at} — {topic} — {status}")

    return "\n".join(lines)
