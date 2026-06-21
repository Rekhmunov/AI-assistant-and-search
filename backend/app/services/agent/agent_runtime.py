"""Единый runtime агента в MAX (webhook)."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import RateLimiter
from app.models.agent import AgentInstance
from app.models.user import User
from app.services.agent.agent_loop import RuntimeLoopResult, run_runtime_loop
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)

_BACKGROUND_MARKERS = (
    "отчет",
    "отчёт",
    "excel",
    "exel",
    "xlsx",
    "сформируй",
    "сформировать",
    "выгруз",
    "за месяц",
    "за неделю",
    "за период",
)


def should_run_max_loop_background(user_text: str) -> bool:
    low = (user_text or "").lower()
    if len(low) > 600:
        return True
    return sum(1 for m in _BACKGROUND_MARKERS if m in low) >= 2


async def run_max_interactive_loop(
    db: AsyncSession,
    redis_client,
    user: User,
    agent: AgentInstance,
    *,
    user_text: str,
    chat_id: int | None = None,
    author: str = "",
    vision_context: str = "",
    bot: MaxBotService | None = None,
) -> RuntimeLoopResult:
    """Unified MAX runtime: tools + reflection + thread memory."""
    _ = bot
    limiter = RateLimiter(redis_client)
    enriched = (user_text or "").strip()
    if vision_context:
        enriched = f"{enriched}\n\n[Анализ изображения]\n{vision_context[:3500]}"

    # Для шаблонных агентов подставляем support_instructions в runtime промпт
    cfg = dict(agent.config or {})
    template = str(cfg.get("template") or "")
    override_runtime_prompt: str | None = None
    if template:
        from app.services.agent.templates.secretary import SECRETARY_RUNTIME_PROMPT
        if template == "secretary":
            from datetime import datetime, timezone
            tz_name = str(cfg.get("timezone") or "Europe/Moscow")
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo(tz_name)
                now_local = datetime.now(tz)
            except Exception:
                now_local = datetime.now(timezone.utc)
            current_date = now_local.strftime("%d.%m.%Y (%A)")
            instructions = str(cfg.get("support_instructions") or "")
            override_runtime_prompt = (
                SECRETARY_RUNTIME_PROMPT
                .replace("{support_instructions}", instructions or "(инструкция не задана)")
                .replace("{current_date}", current_date)
            )

    result = await run_runtime_loop(
        db,
        redis_client,
        user,
        agent,
        limiter,
        thread_id=agent.thread_id,
        user_text=enriched or "Помоги пользователю.",
        chat_id=chat_id,
        author=author,
        override_runtime_prompt=override_runtime_prompt,
    )
    return result


async def deliver_runtime_result(
    bot: MaxBotService,
    *,
    chat_id: int,
    result: RuntimeLoopResult,
) -> bool:
    """Отправляет ответ в MAX, если инструменты ещё не отправили сообщение."""
    text = (result.text or "").strip()
    if not text and not result.attachments:
        return True
    if not text:
        text = "Готово."
    send = await bot.send_message(
        None,
        text,
        attachments=result.attachments or None,
        chat_id=chat_id,
    )
    return send.ok
