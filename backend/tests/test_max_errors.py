from app.services.agent.max_errors import explain_max_send_error


def test_explain_403_group():
    msg = explain_max_send_error('{"code":403}', chat_id=-123)
    assert "403" in msg or "прав" in msg.lower() or "отклонил" in msg.lower()


def test_explain_rate_limit():
    msg = explain_max_send_error("rate_limited", chat_id=-1)
    assert "ограничил" in msg.lower() or "429" in msg
