"""Regression: post-stream steps must not surface as generic server_error."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.user import Plan, User
from app.services.query_router import RouteDecision
from app.services.search_flow import SearchFlowService


def _parse_sse_events(raw: list[str]) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for chunk in raw:
        event = "message"
        data = ""
        for line in chunk.strip().split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            if line.startswith("data:"):
                import json

                data = json.loads(line[5:].strip())
        if data != "" or event != "message":
            out.append((event, data))
    return out


def test_follow_up_task_failure_still_emits_done():
    """Deferred follow-ups must not crash the stream after done."""
    user = User(id=uuid.uuid4(), plan=Plan.FREE, guest_key="g-test")
    thread_id = None

    route = RouteDecision(
        needs_search=False,
        search_query="вавпвап",
        answer_model="lite",
        reason="rules:chitchat",
        intent="chitchat",
    )

    async def _stream_direct(*_a, **_k):
        yield "Ответ "

    mock_llm = MagicMock()
    mock_llm.stream_answer_direct = _stream_direct
    mock_llm.generate_follow_ups = AsyncMock(side_effect=RuntimeError("follow-up boom"))
    mock_llm._build_messages_direct = AsyncMock(return_value=[{"role": "user", "text": "q"}])
    mock_llm._build_messages_search = AsyncMock(return_value=[{"role": "user", "text": "q"}])

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.add = MagicMock()

    class _Scalar:
        def __init__(self, v):
            self._v = v

        def scalar_one_or_none(self):
            return self._v

    mock_db.execute = AsyncMock(return_value=_Scalar(None))

    limiter = MagicMock()
    limiter.check_search_limit = AsyncMock(return_value=(True, 1, 10))
    limiter.check_global_yandex_limit = AsyncMock(return_value=True)
    limiter.release_search = AsyncMock()

    redis = MagicMock()

    events: list[str] = []
    flow = SearchFlowService()

    async def _run():
        with (
            patch("app.services.search_flow.resolve_runtime_providers") as resolve,
            patch.object(flow.router, "route", AsyncMock(return_value=route)),
            patch(
                "app.services.search_flow._messages_have_debug_trace",
                AsyncMock(return_value=False),
            ),
            patch("app.services.search_flow.get_settings") as gs,
        ):
            gs.return_value.follow_ups_deferred = True
            gs.return_value.follow_ups_post_done_timeout_sec = 4.0
            resolve.return_value = (
                mock_llm,
                MagicMock(),
                MagicMock(),
                "anthropic_claude",
                "yandex_search",
            )
            async for ev in flow.stream_search(
                mock_db, user, limiter, "вавпвап", thread_id, redis_client=redis
            ):
                events.append(ev)

    asyncio.run(_run())

    parsed = _parse_sse_events(events)
    codes = [d.get("code") for e, d in parsed if e == "error"]
    assert "server_error" not in codes
    assert any(e == "done" for e, _ in parsed)
