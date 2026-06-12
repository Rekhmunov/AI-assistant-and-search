from app.services.agent.capabilities import user_asks_feasibility, user_wants_immediate_lookup
from app.services.agent.search_reply import prefer_web_search_answer


def test_immediate_lookup_not_feasibility():
    q = "можешь найти курс доллара в интернете"
    assert user_wants_immediate_lookup(q)
    assert not user_asks_feasibility(q)


def test_reminder_still_feasibility():
    q = "Ты можешь сделать напоминание в своем чате?"
    assert user_asks_feasibility(q)
    assert not user_wants_immediate_lookup(q)


def test_prefer_web_search_when_reply_empty():
    """Fallback to web_search text only when LLM reply is empty."""
    trace = [
        {
            "ok": True,
            "tool": "web_search",
            "result": {
                "text": "Курс USD/RUB: 92,5 ₽\n\nИсточники:\n[1] ЦБ РФ",
                "sources": [{"index": 1, "url": "https://cbr.ru"}],
            },
        }
    ]
    # Empty reply → use search text
    assert "92,5" in prefer_web_search_answer("", trace)
    assert "92,5" in prefer_web_search_answer("   ", trace)


def test_trust_llm_reply_when_not_empty():
    """LLM wrote something — trust it, no keyword-based replacement."""
    trace = [
        {
            "ok": True,
            "tool": "web_search",
            "result": {"text": "Курс USD/RUB: 92,5 ₽", "sources": []},
        }
    ]
    # Even if the reply sounds like a refusal, we trust the LLM.
    # The system prompt should prevent such replies — not post-hoc keyword matching.
    reply = "По данным поиска, курс — 92,5 ₽."
    assert prefer_web_search_answer(reply, trace) == reply

    refusal = "Моя задача — помогать с настройкой автоматизации в MAX."
    # We no longer replace non-empty replies by keyword detection.
    assert prefer_web_search_answer(refusal, trace) == refusal


def test_no_web_search_in_trace():
    assert prefer_web_search_answer("Привет", []) == "Привет"
    assert prefer_web_search_answer("", []) == ""
