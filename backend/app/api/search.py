from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_rate_limiter, get_redis
from app.services.app_settings import get_setting
from app.core.limiter import RateLimiter
from app.models.user import User
from app.schemas.search import SearchRequest
from app.services.search_flow import SearchFlowService

router = APIRouter(prefix="/search", tags=["search"])


@router.post("")
async def search_stream(
    body: SearchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
):
    redis = await get_redis()
    if await get_setting("maintenance_mode", db, redis):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Maintenance mode")

    flow = SearchFlowService()

    async def event_generator():
        async for event in flow.stream_search(db, user, limiter, body.query, body.thread_id):
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
