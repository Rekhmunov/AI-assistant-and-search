"""GPT messages preview must tolerate content/text keys."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services.search_debug import build_gpt_messages_preview


def test_preview_accepts_content_key():
    llm = MagicMock()
    llm._build_messages_direct = AsyncMock(
        return_value=[
            {"role": "system", "content": "sys"},
            {"role": "user", "text": "hello"},
        ]
    )

    preview = asyncio.run(
        build_gpt_messages_preview(
            llm,
            llm_query="hello",
            sources=[],
            history=[],
            prior_sources_block="",
            needs_search=False,
            model="lite",
        )
    )

    assert preview == [
        {"role": "system", "text": "sys"},
        {"role": "user", "text": "hello"},
    ]
