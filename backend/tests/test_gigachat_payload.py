"""GigaChat payload validation."""

import pytest

from app.services.gigachat import _ensure_gigachat_payload
from app.services.yandex_errors import YandexServiceError


def test_empty_messages_raises_clear_error():
    with pytest.raises(YandexServiceError, match="пустой запрос"):
        _ensure_gigachat_payload([{"role": "system", "text": "   "}])


def test_user_only_ok():
    out = _ensure_gigachat_payload([{"role": "user", "text": "Привет"}])
    assert out == [{"role": "user", "content": "Привет"}]
