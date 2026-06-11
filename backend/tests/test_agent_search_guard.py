from app.services.agent.search_guard import (
    must_run_search_before_reply,
    reply_looks_hallucinated_search,
    search_tools_ran_ok,
    user_needs_live_search,
)


def test_user_needs_live_search_news():
    assert user_needs_live_search("Найди свежую новость про ИИ")
    assert not user_needs_live_search("Какой у меня chat_id?")


def test_search_tools_ran_ok_requires_result():
    assert search_tools_ran_ok(
        [{"ok": True, "tool": "web_search", "result": {"text": "ответ", "sources": []}}]
    )
    assert not search_tools_ran_ok([{"ok": True, "tool": "max_get_chat", "result": {}}])


def test_hallucination_marker():
    assert reply_looks_hallucinated_search("Вот свежая новость: [пример новости]")


def test_must_run_search_blocks_reply_without_tool():
    assert must_run_search_before_reply(
        user_text="Найди новость про ИИ и напиши в чат",
        reply="Вот свежая новость: [пример новости]. Если хочешь настроить регулярную рассылку…",
        tool_trace=[],
    )


def test_must_run_search_allows_after_tool():
    assert not must_run_search_before_reply(
        user_text="Найди новость про ИИ",
        reply="Краткая сводка по теме.",
        tool_trace=[
            {
                "ok": True,
                "tool": "web_search",
                "result": {"text": "факты", "sources": [{"index": 1, "url": "https://a.ru"}]},
            }
        ],
    )
