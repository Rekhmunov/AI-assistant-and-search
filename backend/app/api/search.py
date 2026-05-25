from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SearchUserResult, get_db, get_rate_limiter, get_redis, get_search_user, set_guest_cookie
from app.services.app_settings import get_setting
from app.core.limiter import RateLimiter
from app.schemas.search import SearchRequest
from app.services.search_flow import SearchFlowService

router = APIRouter(prefix="/search", tags=["search"])


@router.post("")
async def search_stream(
    body: SearchRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[SearchUserResult, Depends(get_search_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
):
    redis = await get_redis()
    if await get_setting("maintenance_mode", db, redis):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Maintenance mode")

    if actor.new_guest_key:
        set_guest_cookie(response, actor.new_guest_key)
        response.headers["X-Guest-Session"] = actor.new_guest_key

    flow = SearchFlowService()
    user = actor.user

    async def event_generator():
        async for event in flow.stream_search(
            db, user, limiter, body.query, body.thread_id, body.attachment_ids
        ):
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
