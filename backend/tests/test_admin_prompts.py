"""Настройки провайдеров и промптов."""

from app.services.app_settings import SETTING_KEYS, default_for_key
from app.services.prompts.catalog import PROMPT_CATALOG, PROMPT_SETTING_KEYS
from app.services.prompts.defaults import DEFAULT_LLM_PROVIDER, DEFAULT_SEARCH_PROVIDER, PROMPT_DEFAULTS


def test_prompt_catalog_matches_defaults():
    assert len(PROMPT_CATALOG) == len(PROMPT_DEFAULTS)
    for p in PROMPT_CATALOG:
        assert p.id in PROMPT_DEFAULTS
        assert p.setting_key in SETTING_KEYS


def test_provider_defaults():
    assert default_for_key("llm_provider") == DEFAULT_LLM_PROVIDER
    assert default_for_key("search_provider") == DEFAULT_SEARCH_PROVIDER


def test_prompt_setting_keys_registered():
    for key in PROMPT_SETTING_KEYS:
        assert key in SETTING_KEYS
