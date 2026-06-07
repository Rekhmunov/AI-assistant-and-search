"""Vision: Alice VLM + fallback-цепочка."""

from app.core.config import Settings
from app.services.providers.registry import VALID_VISION_IDS, list_vision_providers
from app.services.prompts.defaults import DEFAULT_VISION_PROVIDER, PROMPT_DEFAULTS
from app.services.vision_service import (
    VISION_FALLBACK_ORDER,
    _looks_like_refusal,
    build_vision_fallback_chain,
)


def test_default_vision_provider_is_alice_vlm():
    assert DEFAULT_VISION_PROVIDER == "alice_vlm"
    assert "alice_vlm" in VALID_VISION_IDS


def test_vision_fallback_order_default():
    assert build_vision_fallback_chain("alice_vlm") == ("alice_vlm", "gigachat", "anthropic_claude")


def test_vision_fallback_order_when_gigachat_primary():
    assert build_vision_fallback_chain("gigachat") == ("gigachat", "alice_vlm", "anthropic_claude")


def test_vision_fallback_order_when_claude_primary():
    assert build_vision_fallback_chain("anthropic_claude") == (
        "anthropic_claude",
        "alice_vlm",
        "gigachat",
    )


def test_vision_fallback_unknown_primary_falls_back_to_default():
    assert build_vision_fallback_chain("unknown") == build_vision_fallback_chain(DEFAULT_VISION_PROVIDER)
    assert VISION_FALLBACK_ORDER[0] == "alice_vlm"


def test_registry_lists_alice_vlm_first():
    settings = Settings(yandex_folder_id="f", yandex_api_key="k")
    providers = list_vision_providers(settings)
    assert providers[0].id == "alice_vlm"
    assert providers[0].configured is True


def test_alice_vlm_prompt_default_registered():
    assert "alice_vlm_answer_vision" in PROMPT_DEFAULTS


def test_looks_like_refusal_detects_russian_decline():
    assert _looks_like_refusal("Извините, я не могу обработать это изображение.")
    assert not _looks_like_refusal("На фото изображён чайник Bosch, модель видна на упаковке.")
