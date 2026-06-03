from app.services.llm_flow_router import _parse_flow_response


def test_parse_export_chat_document():
    raw = '{"flow": "export_chat_document", "needs_search": false, "answer_model": "lite", "reason": "test"}'
    d = _parse_flow_response(raw)
    assert d is not None
    assert d.flow == "export_chat_document"
    assert d.needs_search is False


def test_parse_search_rag():
    raw = '{"flow": "search_rag", "needs_search": true, "answer_model": "pro", "reason": "facts"}'
    d = _parse_flow_response(raw)
    assert d is not None
    assert d.flow == "search_rag"
