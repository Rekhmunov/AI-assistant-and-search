import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import Settings
from app.models.user import Plan, User
from app.services.app_settings import SETTING_KEYS, default_for_key
from app.services.prompts.defaults import DEFAULT_FREE_LLM_PROVIDER
from app.services.providers.factory import resolve_free_llm_provider_id, resolve_llm_provider_id_for_user
from app.services.providers.registry import VALID_FREE_LLM_IDS


def test_free_llm_provider_in_setting_keys():
    assert "free_llm_provider" in SETTING_KEYS
    assert SETTING_KEYS["free_llm_provider"] is str


def test_free_llm_default_deepseek():
    settings = Settings()
    assert default_for_key("free_llm_provider", settings) == DEFAULT_FREE_LLM_PROVIDER


def test_valid_free_llm_ids():
    assert VALID_FREE_LLM_IDS == frozenset({"deepseek", "gigachat"})


class TestFreeLlmProviderResolve(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_llm_provider_for_pro_vs_free(self):
        db = MagicMock()
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)

        pro_user = User(plan=Plan.PRO)
        free_user = User(plan=Plan.FREE, email="a@b.c")

        with patch(
            "app.services.providers.factory.get_setting",
            new=AsyncMock(side_effect=lambda key, *_a, **_k: "perplexity" if key == "llm_provider" else "deepseek"),
        ):
            self.assertEqual(await resolve_llm_provider_id_for_user(db, redis, pro_user), "perplexity")
            self.assertEqual(await resolve_llm_provider_id_for_user(db, redis, free_user), "deepseek")
            self.assertEqual(await resolve_free_llm_provider_id(db, redis), "deepseek")
