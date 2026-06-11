"""Человекочитаемые статусы шагов агента для SSE и polling."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import redis.asyncio as redis

from app.services.agent.agent_pending import update_agent_pending
from app.services.sse import sse_event

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], Awaitable[None]]

STATUS_THINKING = "Анализирую задачу…"
STATUS_CONTEXT_RESET = "Сбрасываю контекст…"
STATUS_ANALYZING_RESULTS = "Формирую ответ по результатам проверок…"
STATUS_INGEST_FILES = "Обрабатываю загруженные документы…"
STATUS_ADMIN_CHECK = "Проверяю права администратора в группе…"
STATUS_MAX_CHAT = "Запрашиваю данные чата MAX…"
STATUS_PREFLIGHT = "Проверяю группу MAX перед запуском…"
STATUS_ACTIVATING = "Запускаю агента…"
STATUS_FIRST_DISPATCH = "Выполняю первую отправку…"
STATUS_REFLECTING = "Проверяю ответ перед отправкой…"
STATUS_MEMORY_UPDATE = "Обновляю память диалога…"
STATUS_SEARCH_FETCH = "Ищу источники в интернете…"
STATUS_SEARCH_WRITE = "Формирую текст по найденным источникам…"
STATUS_BUILDING_POST = "Собираю пост: текст и иллюстрации…"
STATUS_GENERATING_IMAGES = "Генерирую изображения…"

TOOL_STATUS_LABELS: dict[str, str] = {
    "max_probe_chat": "Проверяю доступ бота к чату MAX…",
    "max_send_test": "Отправляю тестовое сообщение в MAX…",
    "max_get_chat": "Запрашиваю информацию о чате MAX…",
    "max_list_bot_chats": "Получаю список чатов, куда добавлен бот…",
    "max_resolve_channel_link": "Определяю группу по ссылке MAX…",
    "max_read_activity_logs": "Читаю журнал активности агента…",
    "web_search": "Ищу в интернете…",
    "read_thread_summary": "Просматриваю историю диалога…",
    "max_send_file": "Формирую и отправляю файл в MAX…",
    "max_send_message": "Отправляю сообщение в MAX…",
    "search_thread_history": "Ищу в истории диалога…",
    "store_agent_record": "Сохраняю запись…",
    "query_agent_records": "Читаю сохранённые данные…",
    "update_agent_memory": "Обновляю память агента…",
}


def tool_status_label(tool: str) -> str:
    name = str(tool or "").strip().lower()
    return TOOL_STATUS_LABELS.get(name, "Выполняю проверку…")


async def noop_status(_text: str) -> None:
    return None


class AgentStatusReporter:
    """Пишет статус в Redis и отдаёт события SSE через очередь."""

    def __init__(
        self,
        redis_client: redis.Redis,
        thread_id: UUID,
        *,
        user_message_id: UUID | None = None,
    ) -> None:
        self._redis = redis_client
        self._thread_id = thread_id
        self._user_message_id = user_message_id
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._closed = False

    async def emit(self, text: str) -> None:
        status = (text or "").strip()
        if not status:
            return
        try:
            await update_agent_pending(
                self._redis,
                self._thread_id,
                custom_status=status,
                user_message_id=self._user_message_id,
            )
        except Exception:
            logger.warning("agent status redis update failed thread=%s", self._thread_id, exc_info=True)
        await self._queue.put(status)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._queue.put(None)

    def callback(self) -> StatusCallback:
        return self.emit

    async def iter_sse(self):
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield sse_event("status", {"status": item})


async def emit_status(callback: StatusCallback | None, text: str) -> None:
    if callback is None:
        return
    await callback(text)


def message_to_sse_dict(msg: Any) -> dict[str, Any]:
    from app.schemas.thread import MessageOut

    return MessageOut.model_validate(msg).model_dump(mode="json")
