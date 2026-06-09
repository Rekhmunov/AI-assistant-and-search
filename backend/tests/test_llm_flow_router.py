from app.models.user import Plan
from app.services.llm_flow_router import LlmFlowDecision, _normalize_flow, _parse_flow_response


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


def test_normalize_new_document_to_chat():
    decision = LlmFlowDecision(
        flow="export_chat_document",
        needs_search=False,
        answer_model="lite",
        reason="misroute",
    )
    out = _normalize_flow(
        "Сделай документ с характеристикой Yandex GPT 5",
        decision,
        Plan.FREE,
        has_thread_history=False,
    )
    assert out.flow == "chat"
    assert out.needs_search is True
