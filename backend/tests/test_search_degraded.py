"""Деградация при сбое Yandex Search: пустая выдача, без исключения."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.facts.pipeline import FactPipeline
from app.services.yandex_errors import YandexServiceError


@pytest.mark.asyncio
async def test_search_batch_degrades_on_network_error():
    search = MagicMock()
    search.search = AsyncMock(
        side_effect=YandexServiceError("search", "Поиск недоступен (сеть)")
    )
    pipeline = FactPipeline(search=search, llm=MagicMock())

    q, ranked, assessment = await pipeline._search_batch(
        "тест",
        enhance_fn=lambda x: x,
        llm_query="тест",
        slots=[],
        rank_flags={"weather": False, "currency": False},
        howto=False,
        answer_model="lite",
        redis_client=None,
    )

    assert q == "тест"
    assert ranked == []
    assert assessment.ok is False
