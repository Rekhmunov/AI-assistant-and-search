from app.services.agent.agent_tool_feedback import (
    ensure_action_feedback,
    reply_is_deferred_promise,
    summarize_tool_trace_for_user,
)


def test_deferred_promise_detected():
    assert reply_is_deferred_promise("Проверю доступ бота к группе и отправлю сообщение повторно.")
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
            "result": {"chat_id": -123, "message_id": 1, "error": None},
        },
    ]
    summary = summarize_tool_trace_for_user(trace)
    assert summary
    assert "администратор" in summary.lower() or "связь" in summary.lower()
    assert "отправлено" in summary.lower()


def test_ensure_feedback_replaces_promise_after_tools():
    trace = [
        {
            "ok": True,
            "tool": "max_send_message",
            "result": {"chat_id": -99, "message_id": 5},
        }
    ]
    out = ensure_action_feedback("Сейчас отправлю сообщение в группу.", trace, "напиши в группу")
    assert "отправлен" in out.lower()
    assert "сейчас отправлю" not in out.lower()


def test_ensure_feedback_without_tools_and_promise():
    out = ensure_action_feedback(
        "Проверю доступ и отправлю курс.",
        [],
        "напиши курс в группу",
    )
    assert "не удалось" in out.lower() or "повторите" in out.lower()
