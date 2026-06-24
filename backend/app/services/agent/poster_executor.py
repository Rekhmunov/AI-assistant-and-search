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
    topics = cfg.get("poster_topics", "")
    if topics:
        parts.append(f"Темы: {topics}")
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


def _pick_next_topic(agent: AgentInstance) -> str:
    """Выбирает следующую тему по ротации."""
    cfg = _get_cfg(agent)
    # Try structured topics first
    topics_raw = cfg.get("poster_topics", "")
    if not topics_raw:
        instr = str(cfg.get("support_instructions") or "")
        m = re.search(r"темы:\s*(.+?)(?:\.|$)", instr, re.IGNORECASE)
        topics_raw = m.group(1) if m else ""

    topics: list[str] = []
    if topics_raw:
        topics = [t.strip() for t in re.split(r"[;,\n]", topics_raw) if t.strip()]

    if not topics:
        return "общая тема канала"

    last_idx = int(cfg.get("poster_last_topic_idx", -1))
    next_idx = (last_idx + 1) % len(topics)
    cfg["poster_last_topic_idx"] = next_idx
    _save_cfg(agent, cfg)
    return topics[next_idx]


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

def save_pending_draft(
    agent: AgentInstance,
    *,
    post_id: str,
    topic: str,
    text: str,
    draft_message_id: str | None = None,
) -> None:
    cfg = _get_cfg(agent)
    cfg[_DRAFT_PENDING_KEY] = {
        "post_id": post_id,
        "topic": topic,
        "text": text,
        "draft_message_id": draft_message_id,
        "awaiting_edit": False,
    }
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


async def send_draft_for_approval(
    agent: AgentInstance,
    db: AsyncSession,
    bot: MaxBotService,
    *,
    approval_chat_id: int | None = None,
    post_id: str,
    topic: str,
    text: str,
) -> str | None:
    """
    Отправляет черновик с кнопками согласования.
    Если approval_chat_id не указан — определяет назначение из конфига агента.
    Поддерживает как групповой чат, так и DM с владельцем.
    Возвращает message_id отправленного сообщения.
    """
    header = f"📝 **Черновик поста** — тема: _{topic}_\n\n"
    full_text = header + text

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

    # Resolve destination
    if approval_chat_id:
        dest_chat_id, dest_user_id = approval_chat_id, None
    else:
        dest_chat_id, dest_user_id = get_approval_destination(agent)

    if dest_chat_id:
        result = await bot.send_message(
            None, full_text, attachments=[keyboard],
            chat_id=dest_chat_id, notify=True,
        )
    elif dest_user_id:
        result = await bot.send_message(
            dest_user_id, full_text, attachments=[keyboard],
        )
    else:
        logger.warning("send_draft_for_approval: no destination for agent=%s", agent.id)
        return None

    return result.message_id if result.ok else None


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

async def publish_to_channel(
    bot: MaxBotService,
    *,
    channel_id: int,
    text: str,
    image_bytes: bytes | None = None,
) -> bool:
    """Публикует пост в канал. Возвращает True при успехе."""
    attachments = []

    if image_bytes:
        try:
            token = await bot.upload_media(image_bytes, "post_image.jpg", "image")
            if token:
                attachments.append({"type": "image", "payload": {"token": token}})
        except Exception as exc:
            logger.warning("Poster: image upload failed: %s", exc)

    result = await bot.send_message(
        None,
        text,
        attachments=attachments or None,
        chat_id=channel_id,
        notify=True,
    )
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
