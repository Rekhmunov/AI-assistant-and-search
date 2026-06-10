"""Генерация текста напоминаний по инструкции (стишок, совет и т.д.)."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_GENERATION_VERBS_RE = re.compile(
    r"(?:напиши|напишите|сгенерир|придумай|придумайте|составь|составьте|создай|создайте|"
    r"сделай|сделайте|пришли|пришлите|отправь|отправьте|дай|подбери|сочини)",
    re.I,
)

_GENERATION_KIND_RE = re.compile(
    r"(?:стишок|стихотворен|стих\b|шутк|анекдот|рассказ|поздравлен|цитат|"
    r"факт\b|совет|рецепт|мотивац|загадк|сказк|песн|тост\b)",
    re.I,
)

_LITERAL_ONLY_RE = re.compile(
    r"(?:напомни(?:ть)?\s+(?:про|о)|напоминание\s+о|встреч|собрани|звонок|"
    r"взять\s+лекарств|полить|оплатить|не\s+забудь\s+про)",
    re.I,
)


def wants_llm_generated_content(text: str) -> bool:
    """
    Инструкция «напиши стишок» — генерировать при отправке.
    «Напомни про встречу» — отправить текст как есть.
    """
    raw = (text or "").strip()
    if len(raw) < 6:
        return False
    low = raw.lower()
    if _LITERAL_ONLY_RE.search(low) and not _GENERATION_VERBS_RE.search(low):
        return False
    if _GENERATION_KIND_RE.search(low) and _GENERATION_VERBS_RE.search(low):
        return True
    if _GENERATION_KIND_RE.search(low) and re.search(r"\d+\s*строк", low):
        return True
    if re.search(r"(?:просто\s+)?напиши\s+стишок", low):
        return True
    return False


def generation_instruction(text: str) -> str:
    return (text or "").strip()


_GENERATION_SYSTEM_PROMPT = """Ты готовишь текст одного сообщения для мессенджера MAX по инструкции пользователя.
Выполни инструкцию полностью: если просят стишок на 4 строки — напиши короткий стишок ровно из четырёх строк.
Если просят шутку, совет, поздравление — дай готовый текст.
Только итоговый текст сообщения: без кавычек, без пояснений «вот стишок», без markdown-заголовков."""


async def generate_reminder_text(
    db,
    redis_client,
    user,
    instruction: str,
) -> str:
    from app.services.providers.factory import resolve_runtime_providers

    prompt = generation_instruction(instruction)
    if not prompt:
        return "—"

    llm, _, _, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
    try:
        if hasattr(llm, "complete_text"):
            text = await llm.complete_text(  # type: ignore[attr-defined]
                [
                    {"role": "system", "text": _GENERATION_SYSTEM_PROMPT},
                    {"role": "user", "text": prompt[:1500]},
                ],
                model="pro",
                max_tokens=500,
                temperature=0.7,
            )
            body = (text or "").strip()
            if body:
                return body
    except Exception as exc:
        logger.warning("Reminder generation LLM failed: %s", exc)

    return prompt
