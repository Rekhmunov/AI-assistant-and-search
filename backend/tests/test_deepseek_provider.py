"""DeepSeek provider helpers."""

from app.services.deepseek import DeepSeekProvider


def test_text_from_completion_prefers_content():
    llm = DeepSeekProvider()
    text = llm._text_from_completion(
        {"choices": [{"message": {"content": "ответ", "reasoning_content": "думаю"}}]}
    )
    assert text == "ответ"


def test_text_from_completion_falls_back_to_reasoning():
    llm = DeepSeekProvider()
    text = llm._text_from_completion(
        {"choices": [{"message": {"content": "", "reasoning_content": "ок"}}]}
    )
    assert text == "ок"


def test_thinking_disabled_for_stream_and_short_pro():
    llm = DeepSeekProvider()
    assert llm._thinking_payload("lite", max_tokens=1000) == {"thinking": {"type": "disabled"}}
    assert llm._thinking_payload("pro", max_tokens=64, stream=True) == {"thinking": {"type": "disabled"}}
    assert llm._thinking_payload("pro", max_tokens=64)["thinking"]["type"] == "disabled"
    assert llm._thinking_payload("pro", max_tokens=512)["thinking"]["type"] == "enabled"
