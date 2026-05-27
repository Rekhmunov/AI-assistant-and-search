"""Промпты DeepSeek для fenced code blocks."""

from app.services.prompts.defaults import PROMPT_DEFAULTS
from app.services.prompts.deepseek_defaults import DEEPSEEK_ANSWER_PROMPT_IDS


def test_deepseek_answer_prompts_use_fenced_code_instructions():
    for key, text in DEEPSEEK_ANSWER_PROMPT_IDS.items():
        assert "```php" in text or "```" in text
        assert "ЗАПРЕЩЕНО" in text or "ТОЛЬКО" in text
        assert PROMPT_DEFAULTS[key] == text


def test_deepseek_search_differs_from_yandex():
    yandex = PROMPT_DEFAULTS["yandex_gpt_answer_search"]
    deepseek = PROMPT_DEFAULTS["deepseek_answer_search"]
    assert deepseek != yandex
    assert "Glosix, DeepSeek" in deepseek or "DeepSeek" in deepseek
