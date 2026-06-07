"""Answer-промпты по провайдерам (раздельные блоки)."""

from app.services.prompts.anthropic_claude_defaults import ANTHROPIC_ANSWER_PROMPT_IDS
from app.services.prompts.defaults import PROMPT_DEFAULTS
from app.services.prompts.deepseek_defaults import DEEPSEEK_ANSWER_PROMPT_IDS
from app.services.prompts.provider_answer_defaults import PROVIDER_ANSWER_PROMPTS


def test_provider_registry_has_answer_prompt_providers():
    assert set(PROVIDER_ANSWER_PROMPTS) == {
        "alice_vlm",
        "deepseek",
        "anthropic_claude",
        "gigachat",
    }


def test_deepseek_answer_prompts_use_fenced_code_instructions():
    for key, text in DEEPSEEK_ANSWER_PROMPT_IDS.items():
        assert "```" in text
        assert PROMPT_DEFAULTS[key] == text


def test_anthropic_answer_prompts_separate_from_deepseek():
    for key in ANTHROPIC_ANSWER_PROMPT_IDS:
        assert "```" in ANTHROPIC_ANSWER_PROMPT_IDS[key]
        assert PROMPT_DEFAULTS[key] == ANTHROPIC_ANSWER_PROMPT_IDS[key]
    assert (
        PROMPT_DEFAULTS["deepseek_answer_search"]
        != PROMPT_DEFAULTS["anthropic_claude_answer_search"]
    )
    assert "DeepSeek" in PROMPT_DEFAULTS["deepseek_answer_search"]
    assert "Claude" in PROMPT_DEFAULTS["anthropic_claude_answer_search"]


def test_deepseek_search_differs_from_yandex():
    assert PROMPT_DEFAULTS["deepseek_answer_search"] != PROMPT_DEFAULTS["yandex_gpt_answer_search"]
