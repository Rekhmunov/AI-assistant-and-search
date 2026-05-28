"""GigaChat HTTP errors and pro→lite fallback on 402."""

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.gigachat import GigaChatProvider, _gigachat_service_error, _is_gigachat_pro_payment_error
from app.services.yandex_errors import YandexServiceError


def test_402_payment_required_message():
    req = httpx.Request("POST", "https://example.com/chat/completions")
    resp = httpx.Response(402, request=req, text='{"status":402,"message":"Payment Required"}')
    err = httpx.HTTPStatusError("402", request=req, response=resp)
    svc = _gigachat_service_error(err)
    assert isinstance(svc, YandexServiceError)
    assert svc.status_code == 402
    assert "402" in str(svc)
    assert "оплат" in str(svc).lower() or "лимит" in str(svc).lower()


def test_is_pro_payment_error():
    req = httpx.Request("POST", "https://example.com/chat/completions")
    resp = httpx.Response(402, request=req, text="Payment Required")
    err = httpx.HTTPStatusError("402", request=req, response=resp)
    assert _is_gigachat_pro_payment_error(err)


def test_complete_text_pro_402_falls_back_to_lite():
    from app.core.config import Settings

    settings = Settings(gigachat_credentials="dGVzdC1jcmVk")
    llm = GigaChatProvider(settings)
    req = httpx.Request("POST", "https://example.com/chat/completions")
    err_402 = httpx.HTTPStatusError(
        "402",
        request=req,
        response=httpx.Response(402, request=req, text="Payment Required"),
    )

    async def _run():
        with patch("app.services.gigachat.chat_completion_text", new_callable=AsyncMock) as mock_chat:
            mock_chat.side_effect = [err_402, "ok"]
            text = await llm.complete_text([{"role": "user", "text": "hi"}], model="pro")
            assert text == "ok"
            assert mock_chat.call_count == 2
            assert mock_chat.call_args_list[1].args[0]["model"] == llm._model_name("lite")

    asyncio.run(_run())
