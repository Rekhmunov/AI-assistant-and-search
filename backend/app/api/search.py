import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import SearchUserResult, get_rate_limiter, get_redis, get_search_user, set_guest_cookie
from app.core.auth_limits import client_ip
from app.core.database import async_session_factory
from app.core.limiter import RateLimiter
from app.models.user import User
from app.schemas.search import SearchRequest
from app.services.app_settings import get_setting
from app.services.search_flow import SearchFlowService
from app.services.sse import sse_event
from app.services.yandex_errors import YandexServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


@router.post("")
async def search_stream(
    request: Request,
    body: SearchRequest,
    response: Response,
    actor: Annotated[SearchUserResult, Depends(get_search_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
):
    redis = await get_redis()
    async with async_session_factory() as db:
        if await get_setting("maintenance_mode", db, redis):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Делаем сервис лучше, повторите запрос через некоторое время",
            )

    stream_headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    if actor.new_guest_key:
        set_guest_cookie(response, actor.new_guest_key)
        stream_headers["X-Guest-Session"] = actor.new_guest_key

    flow = SearchFlowService()
    user_id: UUID = actor.user.id

    async def event_generator():
        # Отдельная сессия БД: Depends(get_db) закрывается до окончания SSE-стрима.
        async with async_session_factory() as db:
            try:
                result = await db.execute(
                    select(User).where(User.id == user_id, User.deleted_at.is_(None))
                )
                user = result.scalar_one_or_none()
                if not user:
                    yield sse_event("error", {"code": "not_found", "message": "Пользователь не найден"})
                    return
                async for event in flow.stream_search(
                    db,
                    user,
                    limiter,
                    body.query,
                    body.thread_id,
                    body.attachment_ids,
                    redis_client=redis,
                    client_ip=client_ip(request),
                ):
                    yield event
            except YandexServiceError as e:
                logger.warning("Search stream Yandex/Claude error for user %s: %s", user_id, e)
                await db.rollback()
                await limiter.release_search(str(user_id))
                yield sse_event("error", {"code": "yandex_error", "message": str(e)})
            except Exception:
                logger.exception("Search SSE stream failed for user %s", user_id)
                await db.rollback()
                await limiter.release_search(str(user_id))
                yield sse_event(
                    "error",
                    {"code": "server_error", "message": "Ошибка сервера. Попробуйте ещё раз."},
                )

    stream = StreamingResponse(event_generator(), media_type="text/event-stream", headers=stream_headers)
    # Cookies set on injected Response are not always merged into StreamingResponse.
    if actor.new_guest_key:
        for header, value in response.headers.raw:
            if header.lower() == b"set-cookie":
                stream.headers.append("set-cookie", value.decode("latin-1"))
    return stream
