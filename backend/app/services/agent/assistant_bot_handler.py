"""Обработчик личных сообщений для агента «Личный ассистент».

Пайплайн: голос/фото → текст → SearchFlow → ответ в бот.
Прогресс: редактирование сообщения «Думаю...» → «Ищу...» → «Пишу ответ...» → финал.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentStatus
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

# Набор команд ассистента
_ASSISTANT_CMDS = frozenset({"new", "history"})


def _parse_cmd(low: str) -> str | None:
    """Извлекает имя команды из текста вида '/new', 'new', '/new arg'. None если не команда."""
    raw = low.strip()
    if raw.startswith("/"):
        raw = raw[1:]
    word = raw.split()[0] if raw.split() else ""
    return word if word in _ASSISTANT_CMDS else None

_STATUS_ROUTING = "⏳ Обрабатываю запрос…"


async def _find_active_assistant(
    db: AsyncSession, *, max_user_id: int
) -> tuple[AgentInstance, "User"] | None:
    """
    Ищет активного ассистента через пользователя.
    Возвращает (agent, user) или None.
    Надёжнее чем поиск по AgentInstance.max_user_id (может быть 0 при создании).
    """
    user_result = await db.execute(
        select(User).where(User.max_user_id == max_user_id).limit(1)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        return None

    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.user_id == user.id,
            AgentInstance.status == AgentStatus.ACTIVE.value,
        )
    )
    for agent in result.scalars().all():
        if str((agent.config or {}).get("template") or "") == "assistant":
            return agent, user
    return None



def _miniapp_thread_url(thread_id: uuid.UUID, settings) -> str:
    """URL для открытия конкретного треда в мини-приложении MAX."""
    base = (settings.max_bot_url or "").strip().rstrip("/").split("?")[0]
    if not base:
        # Fallback на веб если мини-апп не настроен
        web = (settings.public_web_url or "https://glosix.ru").rstrip("/")
        return f"{web}/thread/{thread_id}"
    return f"{base}?startapp=thread_{thread_id}"


def _open_button(thread_id: uuid.UUID, settings) -> dict:
    """Кнопка «Открыть в Glosix» → открывает мини-приложение MAX."""
    return MaxBotService.make_keyboard_attachment([[{
        "type": "open_app",
        "text": "🔗 Открыть в Glosix",
        "url": _miniapp_thread_url(thread_id, settings),
    }]])


def _truncate(text: str, max_len: int = _MAX_TEXT_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3].rstrip() + "…"



async def _collect_search_result(
    db: AsyncSession,
    user: User,
    redis_client,
    query: str,
    thread_id: uuid.UUID,
    attachment_file_ids: list[uuid.UUID] | None = None,
) -> tuple[str, list[dict], list[str]]:
    """
    Запускает SearchFlowService и собирает ответ + изображения + follow-up вопросы.
    Возвращает (answer_text, images_list, follow_ups_list).
    """
    from app.services.search_flow import SearchFlowService
    from app.core.limiter import RateLimiter
    from app.core.config import get_settings

    settings = get_settings()
    limiter = RateLimiter(redis_client, settings)

    answer_parts: list[str] = []
    images: list[dict] = []
    follow_ups: list[str] = []
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
            event_type, data = _parse_sse(raw_event)
            if event_type == "token":
                text = data.get("text") or ""
                if text:
                    answer_parts.append(text)
            elif event_type == "images":
                imgs = data.get("images")
                if isinstance(imgs, list):
                    images.extend(imgs)
            elif event_type == "follow_ups":
                qs = data.get("questions")
                if isinstance(qs, list):
                    follow_ups = [str(q) for q in qs if q][:3]
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
        return error_msg, [], []

    answer = "".join(answer_parts).strip()
    if not answer:
        answer = "Не удалось получить ответ. Попробуйте переформулировать вопрос."

    return answer, images, follow_ups


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

    bot_base = (settings.max_bot_url or "").strip().rstrip("/").split("?")[0]
    web_base = (settings.public_web_url or "https://glosix.ru").rstrip("/")

    def _thread_btn_url(thread_id) -> str:
        if bot_base:
            return f"{bot_base}?startapp=thread_{thread_id}"
        return f"{web_base}/thread/{thread_id}"

    def _history_url() -> str:
        if bot_base:
            return f"{bot_base}?startapp=history"
        return f"{web_base}/history"

    buttons = []
    for t in threads:
        title = (t.title or "Диалог")[:40]
        ts = t.last_message_at
        label = f"{title} · {ts.strftime('%d.%m %H:%M')}" if ts else title
        buttons.append([{
            "type": "open_app",
            "text": label,
            "url": _thread_btn_url(t.id),
        }])

    # Кнопка «Вся история»
    buttons.append([{
        "type": "open_app",
        "text": "📚 Вся история",
        "url": _history_url(),
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
    used, limit = await limiter.usage_and_limit(user)
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

    found = await _find_active_assistant(db, max_user_id=max_user_id)
    if not found:
        return False
    agent, user = found

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
    cmd = _parse_cmd(low)

    if cmd == "new":
        await _cmd_new(db, redis_client, max_user_id=max_user_id, agent=agent, user=user, bot=bot)
        await db.commit()
        return True

    if cmd == "history":
        await _cmd_history(db, max_user_id=max_user_id, user=user, bot=bot)
        return True


    if not effective_text and not _has_images(payload):
        return False

    # ── Немедленный отбойник ──
    await bot.send_message(max_user_id, _STATUS_ROUTING)

    try:
        # ── Предварительная обработка изображений (vision) ──
        query = (effective_text or "").strip()
        if _has_images(payload):
            vision_text = await _handle_vision(payload, query, bot, max_user_id)
            if vision_text:
                query = vision_text

        if not query:
            await bot.send_message(max_user_id, "Пожалуйста, добавьте текст к сообщению.")
            return True

        # ── Сессионный тред ──
        thread = await get_or_create_session_thread(
            db, redis_client, user=user, agent_id=agent.id
        )

        # ── Запуск поиска ──
        answer, images, follow_ups = await _collect_search_result(
            db, user, redis_client, query, thread.id
        )

        # ── Обновляем TTL сессии в Redis ──
        await touch_session(
            redis_client, user_id=user.id, agent_id=agent.id, thread_id=thread.id
        )

        # ── Отправляем ответ с кнопкой «Открыть в мини-приложении» ──
        answer_truncated = _truncate(answer)
        open_btn = _open_button(thread.id, settings)
        await bot.send_message(max_user_id, answer_truncated, attachments=[open_btn])

        # ── Follow-up вопросы как кнопки (отправляют вопрос в чат при нажатии) ──
        if follow_ups:
            buttons = [[{"type": "message", "text": q[:40], "payload": q}]
                       for q in follow_ups]
            keyboard = MaxBotService.make_keyboard_attachment(buttons)
            await bot.send_message(max_user_id, "Уточнить:", attachments=[keyboard])

        if images:
            await _send_images_to_bot(bot, max_user_id, images, settings)

    except Exception as exc:
        logger.exception("assistant_bot: handle error: %s", exc)
        await bot.send_message(max_user_id, "❌ Произошла ошибка. Попробуйте ещё раз.")

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
