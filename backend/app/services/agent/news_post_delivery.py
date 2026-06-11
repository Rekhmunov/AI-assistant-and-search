"""Новостной пост для MAX: текст 500–1000 символов + 1–3 иллюстрации."""

from __future__ import annotations

import asyncio
import logging
import random
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.agent.image_delivery import build_image_attachments
from app.services.agent.web_digest import build_web_digest_text
from app.services.bot import MaxBotService, UPLOAD_TO_SEND_DELAY_SEC
from app.services.gigachat_image_gen import ImageGenerationError, generate_gigachat_image

logger = logging.getLogger(__name__)

_IMAGE_PROMPTS_SYSTEM = """По новостной сводке предложи от 1 до 3 коротких описаний для иллюстрирующих изображений.
Только визуальные сцены, без текста на картинке. Каждое описание — одна строка, до 120 символов.
Ответь только списком строк, без нумерации и markdown."""


async def _image_prompts_from_summary(
    db: AsyncSession,
    redis_client,
    user: User,
    summary: str,
    *,
    count: int,
) -> list[str]:
    count = max(1, min(3, count))
    from app.services.providers.factory import resolve_runtime_providers

    llm, _, _, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
    try:
        if hasattr(llm, "complete_text"):
            body = await llm.complete_text(  # type: ignore[attr-defined]
                [
                    {"role": "system", "text": _IMAGE_PROMPTS_SYSTEM},
                    {"role": "user", "text": summary[:2500]},
                ],
                model="pro",
                max_tokens=300,
                temperature=0.4,
            )
        else:
            return [f"Иллюстрация к новости: {summary[:120]}"] * count
    except Exception as exc:
        logger.warning("News image prompt LLM failed: %s", exc)
        return [f"Иллюстрация к новости: {summary[:120]}"] * count

    lines = [ln.strip(" -•\t") for ln in (body or "").splitlines() if ln.strip()]
    prompts = [ln for ln in lines if len(ln) >= 12][:3]
    if not prompts:
        prompts = [f"Иллюстрация к новости: {summary[:120]}"]
    if len(prompts) < count:
        prompts.extend([prompts[-1]] * (count - len(prompts)))
    return prompts[:count]


async def _upload_image_attachment(
    image_bytes: bytes,
    *,
    bot: MaxBotService,
    filename: str,
) -> dict | None:
    token = await bot.upload_media(image_bytes, filename, "image")
    if token:
        await asyncio.sleep(UPLOAD_TO_SEND_DELAY_SEC)
        return {"type": "image", "payload": {"token": token}}
    return None


async def build_news_post_attachments(
    db: AsyncSession,
    redis_client,
    user: User,
    summary: str,
    *,
    min_count: int = 1,
    max_count: int = 3,
    bot: MaxBotService | None = None,
) -> list[dict]:
    lo = max(1, min(3, min_count))
    hi = max(lo, min(3, max_count))
    count = random.randint(lo, hi)
    prompts = await _image_prompts_from_summary(db, redis_client, user, summary, count=count)
    bot = bot or MaxBotService()
    attachments: list[dict] = []

    for idx, prompt in enumerate(prompts):
        try:
            result = await generate_gigachat_image(prompt[:2000])
        except ImageGenerationError as exc:
            logger.warning("News post image %s failed: %s", idx + 1, exc)
            continue
        except Exception as exc:
            logger.warning("News post image %s error: %s", idx + 1, exc)
            continue
        att = await _upload_image_attachment(
            result.image_bytes,
            bot=bot,
            filename=f"agent-news-{idx + 1}.jpg",
        )
        if att:
            attachments.append(att)

    if not attachments and prompts:
        text, fallback = await build_image_attachments(prompts[0], bot=bot)
        del text
        return fallback
    return attachments


def _clamp_text_length(text: str, min_chars: int, max_chars: int) -> str:
    body = (text or "").strip()
    if len(body) <= max_chars:
        return body
    cut = body[: max_chars + 1]
    m = re.search(r"(?<=[.!?…])\s", cut[max_chars - 120 :])
    if m:
        end = max_chars - 120 + m.end()
        return cut[:end].strip()
    return cut[:max_chars].rstrip() + "…"


async def build_news_post_content(
    db: AsyncSession,
    redis_client,
    user: User,
    *,
    topic: str,
    header: str = "",
    min_chars: int = 500,
    max_chars: int = 1000,
    image_min: int = 1,
    image_max: int = 3,
    bot: MaxBotService | None = None,
    on_status=None,
) -> tuple[str, list[dict]]:
    from app.services.agent.agent_status import STATUS_BUILDING_POST, STATUS_GENERATING_IMAGES

    if on_status:
        await on_status(STATUS_BUILDING_POST)
    text = await build_web_digest_text(
        db,
        redis_client,
        user,
        topic=topic,
        header=header,
        min_chars=min_chars,
        max_chars=max_chars,
        on_status=on_status,
    )
    text = _clamp_text_length(text, min_chars, max_chars)
    if on_status:
        await on_status(STATUS_GENERATING_IMAGES)
    attachments = await build_news_post_attachments(
        db,
        redis_client,
        user,
        text,
        min_count=image_min,
        max_count=image_max,
        bot=bot,
    )
    return text, attachments
