"""Обработчик личных сообщений для агента «Личный ассистент».

Пайплайн: голос/фото → текст → SearchFlow → ответ в бот.
Прогресс: редактирование сообщения «Думаю...» → «Ищу...» → «Пишу ответ...» → финал.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentStatus
from app.models.message import Message, MessageRole
from app.models.thread import Thread, ThreadType
from app.models.user import Plan, User
from app.services.agent.session_thread import (
    clear_session,
    get_or_create_session_thread,
    touch_session,
)
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)

_MAX_TEXT_LEN = 3800  # MAX лимит 4000, оставляем запас на кнопку/ссылку

# Статусные сообщения-прогресс
_STATUS_ROUTING = "⏳ Обрабатываю запрос…"
_STATUS_SEARCH = "🔍 Ищу информацию…"
_STATUS_ANSWER = "✍️ Составляю ответ…"
_STATUS_IMAGE = "🎨 Генерирую изображение…"


async def _find_active_assistant(
    db: AsyncSession, *, max_user_id: int
) -> AgentInstance | None:
    """Ищет активного ассистента для пользователя."""
    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.max_user_id == max_user_id,
            AgentInstance.status == AgentStatus.ACTIVE.value,
            AgentInstance.config["template"].astext == "assistant",
        )
    )
    return result.scalars().first()


async def _get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


def _web_thread_url(thread_id: uuid.UUID, settings) -> str:
    base = (settings.public_web_url or "https://glosix.ru").rstrip("/")
    return f"{base}/thread/{thread_id}"


def _open_button(thread_id: uuid.UUID, settings) -> dict:
    return MaxBotService.make_keyboard_attachment([[{
        "type": "link",
        "text": "🔗 Открыть в Glosix",
        "url": _web_thread_url(thread_id, settings),
    }]])


def _truncate(text: str, max_len: int = _MAX_TEXT_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3].rstrip() + "…"


async def _save_messages(
    db: AsyncSession,
    thread: Thread,
    user_text: str,
    assistant_text: str,
) -> None:
    """Сохраняет сообщения пользователя и ассистента в тред."""
    now = datetime.now(timezone.utc)
    user_msg = Message(thread_id=thread.id, role=MessageRole.USER, content=user_text)
    asst_msg = Message(thread_id=thread.id, role=MessageRole.ASSISTANT, content=assistant_text)
    db.add(user_msg)
    db.add(asst_msg)
    thread.message_count = (thread.message_count or 0) + 2
    thread.last_message_at = now
    await db.flush()


async def _collect_search_result(
    db: AsyncSession,
    user: User,
    redis_client,
    query: str,
    thread_id: uuid.UUID,
    attachment_file_ids: list[uuid.UUID] | None = None,
) -> tuple[str, list[dict]]:
    """
    Запускает SearchFlowService и собирает финальный ответ + изображения.
    Возвращает (answer_text, images_list).
    """
    from app.services.search_flow import SearchFlowService
    from app.core.limiter import RateLimiter
    from app.core.config import get_settings

    settings = get_settings()
    limiter = RateLimiter(redis_client, settings)

    answer_parts: list[str] = []
    images: list[dict] = []
    error_msg: str | None = None

    flow = SearchFlowService()
    try:
        async for raw_event in flow.stream_search(
            db,
            user,
            limiter,
            query,
            thread_id,
            attachment_ids=attachment_file_ids or [],
            redis_client=redis_client,
            client_ip=None,
        ):
            # SSE event формат: "event: TYPE\ndata: JSON\n\n"
            event_type, data = _parse_sse(raw_event)
            if event_type == "token":
                text = data.get("text") or ""
                if text:
                    answer_parts.append(text)
            elif event_type == "images":
                imgs = data.get("images")
                if isinstance(imgs, list):
                    images.extend(imgs)
            elif event_type == "error":
                code = data.get("code", "")
                if code in ("rate_limit", "free_rate_limit", "guest_rate_limit"):
                    error_msg = (
                        "❌ Дневной лимит запросов исчерпан. "
                        "Попробуйте завтра или проверьте тариф в Glosix."
                    )
                elif code == "free_image_gen_pro":
                    error_msg = "❌ Генерация картинок доступна только в тарифе Pro."
                else:
                    error_msg = data.get("message") or "❌ Не удалось обработать запрос."
                break
    except Exception as exc:
        logger.exception("assistant_bot: search flow error: %s", exc)
        error_msg = "❌ Произошла ошибка при обработке запроса. Попробуйте ещё раз."

    if error_msg:
        return error_msg, []

    answer = "".join(answer_parts).strip()
    if not answer:
        answer = "Не удалось получить ответ. Попробуйте переформулировать вопрос."

    return answer, images


def _parse_sse(raw: str) -> tuple[str, dict]:
    """Парсит строку SSE в (event_type, data_dict)."""
    event_type = ""
    data_str = ""
    for line in raw.strip().split("\n"):
        if line.startswith("event: "):
            event_type = line[7:].strip()
        elif line.startswith("data: "):
            data_str = line[6:].strip()
    try:
        data = json.loads(data_str) if data_str else {}
    except json.JSONDecodeError:
        data = {}
    return event_type, data


async def _send_images_to_bot(
    bot: MaxBotService,
    max_user_id: int,
    images: list[dict],
    settings,
) -> None:
    """Скачивает сгенерированные изображения и отправляет в MAX."""
    import httpx

    for img in images[:3]:  # не более 3 картинок
        url = (img.get("url") or "").strip()
        if not url:
            continue
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
            if resp.status_code == 200:
                token = await bot.upload_media(resp.content, "image.jpg", "image")
                if token:
                    import asyncio
                    await asyncio.sleep(1.0)
                    await bot.send_message(
                        max_user_id,
                        "",
                        attachments=[{"type": "image", "payload": {"token": token}}],
                    )
        except Exception as exc:
            logger.warning("assistant_bot: image send failed: %s", exc)


async def _cmd_new(
    db: AsyncSession,
    redis_client,
    *,
    max_user_id: int,
    agent: AgentInstance,
    user: User,
    bot: MaxBotService,
) -> None:
    """Команда /new — сбросить сессию, начать новый тред."""
    await clear_session(redis_client, user_id=user.id, agent_id=agent.id)
    # Создаём новый тред заранее, чтобы показать его в ответе
    thread = await get_or_create_session_thread(
        db, redis_client, user=user, agent_id=agent.id
    )
    await db.commit()
    from app.core.config import get_settings
    settings = get_settings()
    await bot.send_message(
        max_user_id,
        "🆕 Начат новый диалог. Задавайте вопрос!",
        attachments=[_open_button(thread.id, settings)],
    )


async def _cmd_history(
    db: AsyncSession,
    *,
    max_user_id: int,
    user: User,
    bot: MaxBotService,
) -> None:
    """Команда /history — последние 5 тредов в виде кнопок."""
    from sqlalchemy import nulls_last
    from app.core.config import get_settings
    settings = get_settings()

    # Последние 5 тредов (не закреплённых, не agent-треды)
    result = await db.execute(
        select(Thread)
        .where(
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
            Thread.thread_type == ThreadType.SEARCH,
            Thread.pinned_at.is_(None),
        )
        .order_by(Thread.last_message_at.desc())
        .limit(5)
    )
    threads = result.scalars().all()

    if not threads:
        await bot.send_message(max_user_id, "История пуста. Начните новый диалог!")
        return

    base = (settings.public_web_url or "https://glosix.ru").rstrip("/")
    buttons = []
    for t in threads:
        title = (t.title or "Диалог")[:40]
        ts = t.last_message_at
        if ts:
            label = f"{title} · {ts.strftime('%d.%m %H:%M')}"
        else:
            label = title
        buttons.append([{
            "type": "link",
            "text": label,
            "url": f"{base}/thread/{t.id}",
        }])

    # Кнопка «Вся история»
    buttons.append([{
        "type": "link",
        "text": "📚 Вся история",
        "url": f"{base}/history",
    }])

    keyboard = MaxBotService.make_keyboard_attachment(buttons)
    await bot.send_message(
        max_user_id,
        "Последние диалоги:",
        attachments=[keyboard],
    )


async def _cmd_status(
    *,
    max_user_id: int,
    user: User,
    redis_client,
    bot: MaxBotService,
) -> None:
    """Команда /status — остаток запросов."""
    from app.core.limiter import RateLimiter
    from app.core.config import get_settings
    settings = get_settings()
    limiter = RateLimiter(redis_client, settings)
    used, limit = await limiter.get_search_usage(str(user.id), user.plan)
    plan_label = "Pro" if user.plan == Plan.PRO else "Free"
    remaining = max(0, limit - used)
    text = (
        f"📊 Статус аккаунта:\n"
        f"Тариф: {plan_label}\n"
        f"Использовано сегодня: {used} / {limit}\n"
        f"Осталось: {remaining} запросов"
    )
    await bot.send_message(max_user_id, text)


async def handle_assistant_dm(
    db: AsyncSession,
    redis_client,
    *,
    max_user_id: int,
    text: str,
    payload: dict[str, Any],
    message_id_value: str | None = None,
    bot: MaxBotService | None = None,
) -> bool:
    """
    Основная точка входа для DM-сообщений к «Личному ассистенту».
    Возвращает True если сообщение обработано.
    """
    bot = bot or MaxBotService()

    agent = await _find_active_assistant(db, max_user_id=max_user_id)
    if not agent:
        return False

    user = await _get_user_by_id(db, agent.user_id)
    if not user:
        logger.warning("assistant_bot: user not found for agent %s", agent.id)
        return False

    from app.core.config import get_settings
    settings = get_settings()

    # ── Голосовое сообщение ──
    effective_text = text
    from app.services.agent.max_media import transcribe_voice_message
    if not effective_text and payload:
        voice_text = await transcribe_voice_message(payload)
        if voice_text:
            effective_text = voice_text
            logger.info("assistant_bot: voice transcribed len=%s", len(voice_text))

    low = (effective_text or "").strip().lower()

    # ── Slash-команды ──
    if low in {"/new", "new"}:
        await _cmd_new(db, redis_client, max_user_id=max_user_id, agent=agent, user=user, bot=bot)
        await db.commit()
        return True

    if low in {"/history", "history"}:
        await _cmd_history(db, max_user_id=max_user_id, user=user, bot=bot)
        return True

    if low in {"/status", "status"}:
        await _cmd_status(max_user_id=max_user_id, user=user, redis_client=redis_client, bot=bot)
        return True

    if low in {"/help", "help", "помощь"}:
        help_text = (
            "Команды:\n"
            "/new — начать новый диалог\n"
            "/history — последние беседы\n"
            "/status — остаток запросов\n\n"
            "Просто пишите вопрос — отвечу как Glosix."
        )
        await bot.send_message(max_user_id, help_text)
        return True

    if not effective_text and not _has_images(payload):
        return False

    # ── Отправляем статус «Думаю…» и редактируем по мере прогресса ──
    sent = await bot.send_message(max_user_id, _STATUS_ROUTING)
    progress_mid = sent.message_id if sent.ok else None

    async def _update_progress(status: str) -> None:
        if progress_mid:
            await bot.edit_message(progress_mid, status)

    await _update_progress(_STATUS_SEARCH)

    # ── Обработка изображений из MAX (vision) ──
    query = (effective_text or "").strip()
    if _has_images(payload):
        vision_text = await _handle_vision(payload, query, bot, max_user_id)
        if vision_text:
            query = vision_text
            # Для vision отвечаем прямо из vision, без search_flow
            answer = vision_text
            thread = await get_or_create_session_thread(
                db, redis_client, user=user, agent_id=agent.id
            )
            await _save_messages(db, thread, effective_text or "[фото]", answer)
            await touch_session(redis_client, user_id=user.id, agent_id=agent.id, thread_id=thread.id)
            await db.commit()
            answer_truncated = _truncate(answer)
            if progress_mid:
                await bot.edit_message(progress_mid, answer_truncated,)
            else:
                await bot.send_message(max_user_id, answer_truncated)
            return True

    if not query:
        if progress_mid:
            await bot.edit_message(progress_mid, "Пожалуйста, добавьте текст к сообщению.")
        return True

    # ── Сессионный тред ──
    thread = await get_or_create_session_thread(
        db, redis_client, user=user, agent_id=agent.id
    )

    await _update_progress(_STATUS_ANSWER)

    # ── Запуск поиска ──
    answer, images = await _collect_search_result(
        db, user, redis_client, query, thread.id
    )

    # ── Сохраняем в историю ──
    await _save_messages(db, thread, query, answer)
    await touch_session(redis_client, user_id=user.id, agent_id=agent.id, thread_id=thread.id)
    await db.commit()

    # ── Отправляем ответ ──
    answer_truncated = _truncate(answer)
    open_btn = _open_button(thread.id, settings)

    if progress_mid:
        await bot.edit_message(progress_mid, answer_truncated)
        # Кнопку добавляем отдельным сообщением (edit_message не поддерживает attachments)
        if len(answer) > 100:
            await bot.send_message(max_user_id, "", attachments=[open_btn])
    else:
        await bot.send_message(max_user_id, answer_truncated, attachments=[open_btn])

    # ── Отправляем изображения если есть ──
    if images:
        await _send_images_to_bot(bot, max_user_id, images, settings)

    return True


def _has_images(payload: dict[str, Any]) -> bool:
    from app.services.agent.max_media import message_has_images
    return message_has_images(payload)


async def _handle_vision(
    payload: dict[str, Any],
    text: str,
    bot: MaxBotService,
    max_user_id: int,
) -> str | None:
    """Загружает фото из MAX и получает описание через vision."""
    from app.services.agent.max_media import load_message_vision_images
    from app.services.vision_service import summarize_vision_for_search

    images = await load_message_vision_images(payload, bot=bot)
    if not images:
        return None

    query = text or "Опиши что на изображении."
    try:
        result = await summarize_vision_for_search(images, query)
        return result
    except Exception as exc:
        logger.warning("assistant_bot: vision failed: %s", exc)
        return None
