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
    agent.config = cfg


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


def _build_style_from_config(agent: AgentInstance) -> str:
    """Build human-readable style instructions from structured poster config keys."""
    cfg = _get_cfg(agent)
    parts = []
    topic_list = _get_topic_list(agent)
    if topic_list:
        parts.append(f"Темы: {'; '.join(topic_list)}")
    mode_labels = {"random": "случайный", "no_repeat": "случайный без повторов",
                   "sequential": "по очереди", "priority": "приоритетный"}
    mode = cfg.get("poster_topic_mode", "no_repeat")
    parts.append(f"Порядок тем: {mode_labels.get(mode, mode)}")
    tone = cfg.get("poster_tone", "")
    tone_map = {"official": "официальный", "informal": "неформальный", "expert": "экспертный", "inspiring": "вдохновляющий"}
    if tone:
        parts.append(f"Тон: {tone_map.get(tone, tone)}")
    emoji = cfg.get("poster_emoji", True)
    parts.append(f"Эмодзи: {'да' if emoji else 'нет'}")
    length = cfg.get("poster_length", "medium")
    length_map = {"short": "короткий (~500 зн.)", "medium": "средний (~1000 зн.)", "long": "длинный (~2000 зн.)"}
    parts.append(f"Длина: {length_map.get(length, length)}")
    cta = cfg.get("poster_cta", False)
    parts.append(f"CTA: {'да' if cta else 'нет'}")
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


def _parse_style_instructions(agent: AgentInstance) -> str:
    cfg = _get_cfg(agent)
    # Prefer structured config over legacy text-based instructions
    if cfg.get("poster_topics"):
        return _build_style_from_config(agent)
    return str(cfg.get("support_instructions") or "")


def _get_topic_list(agent: AgentInstance) -> list[str]:
    """Return list of topics, supporting both new (poster_topic_list) and legacy (poster_topics) formats."""
    cfg = _get_cfg(agent)

    # New format: structured list
    topic_list = cfg.get("poster_topic_list")
    if isinstance(topic_list, list):
        topics = [str(t).strip() for t in topic_list if str(t).strip()]
        if topics:
            return topics

    # Legacy: semicolon-separated string
    topics_raw = cfg.get("poster_topics", "")
    if not topics_raw:
        instr = str(cfg.get("support_instructions") or "")
        m = re.search(r"темы:\s*(.+?)(?:\.|$)", instr, re.IGNORECASE)
        topics_raw = m.group(1) if m else ""

    if topics_raw:
        return [t.strip() for t in re.split(r"[;,\n]", topics_raw) if t.strip()]
    return []


def _pick_next_topic(agent: AgentInstance) -> str:
    """
    Выбирает следующую тему согласно настроенному режиму ротации.

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
        return "общая тема канала"
    if len(topics) == 1:
        return topics[0]

    mode = cfg.get("poster_topic_mode", "no_repeat")
    last_idx = int(cfg.get("poster_last_topic_idx", -1))

    if mode == "random":
        idx = _random.randrange(len(topics))

    elif mode == "sequential":
        idx = (last_idx + 1) % len(topics)

    elif mode == "priority":
        # Descending weights: topic 0 gets weight N, topic N-1 gets weight 1
        n = len(topics)
        weights = [n - i for i in range(n)]
        idx = _random.choices(range(n), weights=weights, k=1)[0]

    else:  # "no_repeat" (default)
        # Pick randomly from all except the last-used topic
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
        "text": text[:500],
        "status": status,
        "channel_id": channel_id,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    cfg["poster_history"] = history[-_MAX_HISTORY:]
    _save_cfg(agent, cfg)


def get_post_history(agent: AgentInstance) -> list[dict]:
    cfg = _get_cfg(agent)
    return list(cfg.get("poster_history", []))


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
    """Update image_file_ids in pending draft without touching other fields."""
    cfg = _get_cfg(agent)
    draft = cfg.get(_DRAFT_PENDING_KEY, {})
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
    logger.info("POSTER_IMG agent=%s poster_media=%s topic=%s", agent.id, media_mode, topic[:50])
    if media_mode != "ai":
        logger.info("POSTER_IMG skipped: poster_media=%s (not 'ai')", media_mode)
        return None
    try:
        from app.services.image_gen_service import generate_image, resolve_image_gen_provider_id
        provider_id = await resolve_image_gen_provider_id(db, redis_client)
        logger.info("POSTER_IMG generating with provider=%s prompt=%s...", provider_id, topic[:40])
        img_prompt = f"{topic}. {post_text[:150]}"
        image_bytes, _ = await generate_image(img_prompt, provider_id)
        logger.info("POSTER_IMG success: %d bytes", len(image_bytes))
        return image_bytes
    except Exception as exc:
        logger.warning("POSTER_IMG FAILED (topic=%s): %s", topic, exc)
        return None


async def generate_post(
    agent: AgentInstance,
    topic: str,
    llm,
) -> str:
    """
    Генерирует пост с одним кругом рефлексии (если включена).
    Возвращает финальный текст поста.
    """
    from app.services.agent.templates.poster import (
        POSTER_GENERATION_PROMPT,
        POSTER_REFLECTION_PROMPT,
    )

    style = _parse_style_instructions(agent)
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y")

    # Шаг 1: Генерация черновика
    gen_messages = [
        {"role": "user", "text": POSTER_GENERATION_PROMPT.format(
            topic=topic,
            style_instructions=style[:1500],
            current_date=today,
        )}
    ]
    draft = await llm.complete_text(gen_messages, model="pro", max_tokens=2000, temperature=0.7)
    draft = (draft or "").strip()

    if not draft:
        return f"Пост на тему: {topic}\n\n[Не удалось сгенерировать контент]"

    # Шаг 2: Рефлексия (если включена)
    if get_reflection_enabled(agent):
        try:
            refl_messages = [
                {"role": "user", "text": POSTER_REFLECTION_PROMPT.format(
                    topic=topic,
                    style_instructions=style[:1500],
                    draft=draft,
                )}
            ]
            refined = await llm.complete_text(refl_messages, model="pro", max_tokens=2000, temperature=0.3)
            refined = (refined or "").strip()
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
    full_text = header + text
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
