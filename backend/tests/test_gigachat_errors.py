"""GigaChat HTTP errors → понятные сообщения."""

import httpx
import pytest

from app.services.gigachat import _gigachat_service_error
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
