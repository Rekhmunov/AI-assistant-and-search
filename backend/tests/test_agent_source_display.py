from app.services.agent.source_display import (
    extract_sources_from_tool_trace,
    prepare_agent_reply_for_ui,
    strip_sources_footer,
)


def test_strip_sources_footer():
    raw = "Курс: 92 ₽\n\nИсточники:\n[1] ЦБ — https://cbr.ru"
    assert strip_sources_footer(raw) == "Курс: 92 ₽"


def test_extract_sources_from_tool_trace():
    trace = [
        {
            "ok": True,
            "tool": "web_search",
            "result": {
                "text": "x",
                "sources": [
                    {
                        "index": 1,
                        "url": "https://cbr.ru",
                        "title": "ЦБ",
                        "snippet": "s",
                        "domain": "cbr.ru",
                    }
                ],
            },
        }
    ]
    out = extract_sources_from_tool_trace(trace)
    assert out and out[0]["url"] == "https://cbr.ru"


def test_prepare_agent_reply_for_ui():
    trace = [
        {
            "ok": True,
            "tool": "web_search",
            "result": {
                "text": "Курс 92\n\nИсточники:\n[1] ЦБ — https://cbr.ru",
                "sources": [{"index": 1, "url": "https://cbr.ru", "title": "ЦБ", "domain": "cbr.ru"}],
            },
        }
    ]
    reply = "Курс 92\n\nИсточники:\n[1] ЦБ — https://cbr.ru"
    body, sources = prepare_agent_reply_for_ui(reply, trace)
    assert body == "Курс 92"
    assert sources and len(sources) == 1
