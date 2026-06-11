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


def test_prefer_web_search_over_refusal():
    trace = [
        {
            "ok": True,
            "tool": "web_search",
            "result": {
                "text": "Курс USD/RUB: 92,5 ₽\n\nИсточники:\n[1] ЦБ РФ — https://cbr.ru",
                "sources": [{"index": 1, "url": "https://cbr.ru"}],
            },
        }
    ]
    reply = "Нет, я не могу искать курс доллара. Моя задача — помогать с настройкой автоматизации в MAX."
    out = prefer_web_search_answer(reply, trace)
    assert "92,5" in out
    assert "Источники" in out
    assert "настройк" not in out.lower()
