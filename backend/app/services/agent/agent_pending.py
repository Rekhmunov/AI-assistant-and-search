"""Redis-состояние активного запроса агента (для polling answer-status)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)

PENDING_KEY_PREFIX = "agent:pending:"
PENDING_TTL_SEC = 15 * 60

AgentPhase = str  # thinking | tooling | activating


def _key(thread_id: uuid.UUID | str) -> str:
    return f"{PENDING_KEY_PREFIX}{thread_id}"


async def set_agent_pending(
    redis_client: redis.Redis,
    thread_id: uuid.UUID,
    *,
    user_message_id: uuid.UUID,
    phase: AgentPhase = "thinking",
    custom_status: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "user_message_id": str(user_message_id),
        "phase": phase,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if custom_status:
        payload["custom_status"] = custom_status
    try:
        await redis_client.set(_key(thread_id), json.dumps(payload), ex=PENDING_TTL_SEC)
    except Exception:
        logger.warning("set_agent_pending failed for thread %s", thread_id, exc_info=True)


async def update_agent_pending(
    redis_client: redis.Redis,
    thread_id: uuid.UUID,
    *,
    phase: AgentPhase | None = None,
    custom_status: str | None = None,
    user_message_id: uuid.UUID | None = None,
) -> None:
    try:
        raw = await redis_client.get(_key(thread_id))
        if not raw:
            if user_message_id is None:
                return
            await set_agent_pending(
                redis_client,
                thread_id,
                user_message_id=user_message_id,
                phase=phase or "thinking",
                custom_status=custom_status,
            )
            return
        data = json.loads(raw)
        if phase is not None:
            data["phase"] = phase
        if custom_status is not None:
            data["custom_status"] = custom_status
        if user_message_id is not None:
            data["user_message_id"] = str(user_message_id)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await redis_client.set(_key(thread_id), json.dumps(data), ex=PENDING_TTL_SEC)
    except Exception:
        logger.warning("update_agent_pending failed for thread %s", thread_id, exc_info=True)


async def clear_agent_pending(redis_client: redis.Redis, thread_id: uuid.UUID) -> None:
    try:
        await redis_client.delete(_key(thread_id))
    except Exception:
        logger.warning("clear_agent_pending failed for thread %s", thread_id, exc_info=True)


async def get_agent_pending(redis_client: redis.Redis, thread_id: uuid.UUID) -> dict[str, Any] | None:
    try:
        raw = await redis_client.get(_key(thread_id))
        if not raw:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        logger.warning("get_agent_pending failed for thread %s", thread_id, exc_info=True)
        return None
