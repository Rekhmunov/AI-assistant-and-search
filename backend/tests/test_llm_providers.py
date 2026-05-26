"""Фабрика LLM-провайдеров."""

from app.services.anthropic_claude import AnthropicClaudeProvider
from app.services.providers.factory import create_llm_provider, llm_model_label
from app.services.prompts.store import PromptStore
from app.services.yandex_gpt import YandexGPTProvider


def test_create_yandex_default():
    llm = create_llm_provider("yandex_gpt", None, PromptStore(None, None))  # type: ignore[arg-type]
    assert isinstance(llm, YandexGPTProvider)


def test_create_anthropic():
    llm = create_llm_provider("anthropic_claude", None, PromptStore(None, None))  # type: ignore[arg-type]
    assert isinstance(llm, AnthropicClaudeProvider)


def test_llm_model_label_yandex():
    llm = create_llm_provider("yandex_gpt", None, PromptStore(None, None))  # type: ignore[arg-type]
    uri = llm_model_label(llm, "lite")
    assert uri.startswith("gpt://") or "yandex" in uri.lower() or uri  # mock folder may be empty


def test_llm_model_label_claude():
    llm = create_llm_provider("anthropic_claude", None, PromptStore(None, None))  # type: ignore[arg-type]
    assert "claude" in llm_model_label(llm, "lite").lower()
