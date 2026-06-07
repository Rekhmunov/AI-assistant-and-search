"""Реестр answer-промптов по LLM-провайдеру (раздельные настройки UI/формата).

- yandex_gpt — базовые промпты в defaults.py (ANSWER_*)
- deepseek — deepseek_defaults.py (fenced ``` для DeepSeek API)
- anthropic_claude — anthropic_claude_defaults.py (свои правила для Claude)

Пайплайн (rewriter, extract, follow_ups) общий по копии yandex; меняются только answer_*.
Админка: отдельные поля prompt_{provider}_answer_* в настройках.
"""

from __future__ import annotations

from app.services.prompts.alice_vlm_defaults import ALICE_VLM_ANSWER_PROMPT_IDS
from app.services.prompts.anthropic_claude_defaults import ANTHROPIC_ANSWER_PROMPT_IDS
from app.services.prompts.deepseek_defaults import DEEPSEEK_ANSWER_PROMPT_IDS
from app.services.prompts.gigachat_defaults import GIGACHAT_ANSWER_PROMPT_IDS

# id провайдера из registry / llm_provider → словарь prompt_id → текст
PROVIDER_ANSWER_PROMPTS: dict[str, dict[str, str]] = {
    "alice_vlm": ALICE_VLM_ANSWER_PROMPT_IDS,
    "deepseek": DEEPSEEK_ANSWER_PROMPT_IDS,
    "anthropic_claude": ANTHROPIC_ANSWER_PROMPT_IDS,
    "gigachat": GIGACHAT_ANSWER_PROMPT_IDS,
}

SUPPORTED_SYNC_PROVIDERS = frozenset(PROVIDER_ANSWER_PROMPTS.keys())


def answer_prompts_for_provider(provider_id: str) -> dict[str, str]:
    return PROVIDER_ANSWER_PROMPTS.get(provider_id, {})
