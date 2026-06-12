from app.services.agent.agent_tool_feedback import (
    ensure_action_feedback,
    reply_is_deferred_promise,
    summarize_tool_trace_for_user,
)


def test_deferred_promise_no_longer_replaced():
    # reply_is_deferred_promise is deprecated — always returns False
    assert not reply_is_deferred_promise("Проверю доступ бота к группе и отправлю сообщение.")
    assert not reply_is_deferred_promise("Сообщение отправлено в группу MAX.")


def test_summarize_probe_and_send():
    trace = [
        {
            "ok": True,
            "tool": "max_probe_chat",
            "result": {
                "ok": True,
                "title": "Тест",
                "bot_is_admin": True,
                "explanation": "Связь с чатом MAX в порядке. Бот — администратор.",
            },
        },
        {
            "ok": True,
            "tool": "max_send_message",
            "result": {"chat_id": -123, "message_id": 1},
        },
    ]
    summary = summarize_tool_trace_for_user(trace)
    assert summary
    assert "администратор" in summary.lower() or "связь" in summary.lower()
    assert "отправлено" in summary.lower()


def test_ensure_feedback_trusts_llm_reply():
    # Now LLM reply is trusted, even if it sounds like a "promise"
    trace = [
        {
            "ok": True,
            "tool": "max_send_message",
            "result": {"chat_id": -99, "message_id": 5},
        }
    ]
    llm_reply = "Сообщение отправлено в группу."
    out = ensure_action_feedback(llm_reply, trace, "напиши в группу")
    assert out == llm_reply  # LLM reply is preserved


def test_ensure_feedback_fallback_on_empty_reply():
    trace = [
        {
            "ok": True,
            "tool": "max_send_message",
            "result": {"chat_id": -99, "message_id": 5},
        }
    ]
    out = ensure_action_feedback("", trace, "напиши в группу")
    assert out  # Should return something (tool summary or fallback)
    assert "отправлено" in out.lower() or len(out) > 0


def test_ensure_feedback_error_in_trace():
    trace = [
        {
            "ok": False,
            "tool": "max_send_message",
            "error": "HTTP 403",
            "error_human": "У бота нет прав отправлять в эту группу.",
        }
    ]
    out = ensure_action_feedback("", trace, "напиши в группу")
    assert "не удалось" in out.lower() or "прав" in out.lower()
