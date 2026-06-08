"""Alice AI VLM: auth, model URI candidates."""

from app.core.config import Settings
from app.services.alice_vlm import AliceVLMProvider


def test_alice_vlm_headers_use_api_key_and_folder():
    provider = AliceVLMProvider(
        Settings(yandex_api_key="secret-key", yandex_folder_id="b1gfolder")
    )
    headers = provider._headers()
    assert headers["Authorization"] == "Api-Key secret-key"
    assert headers["x-folder-id"] == "b1gfolder"
    assert headers["x-data-logging-enabled"] == "false"


def test_alice_vlm_model_uri_candidates_include_gemma_fallback():
    provider = AliceVLMProvider(
        Settings(
            yandex_folder_id="b1gfolder",
            yandex_alice_vlm_model="aliceai-vlm/latest",
        )
    )
    assert provider._model_uri_candidates() == [
        "gpt://b1gfolder/aliceai-vlm/latest",
        "gpt://b1gfolder/aliceai-vlm",
        "gpt://b1gfolder/gemma-3-27b-it/latest",
        "gpt://b1gfolder/gemma-3-27b-it",
    ]


def test_alice_vlm_model_uri_candidates_custom_suffix():
    provider = AliceVLMProvider(
        Settings(
            yandex_folder_id="b1gfolder",
            yandex_alice_vlm_model="aliceai-vlm",
            yandex_vision_gemma_model="gemma-3-27b-it",
        )
    )
    assert provider._model_uri_candidates() == [
        "gpt://b1gfolder/aliceai-vlm",
        "gpt://b1gfolder/aliceai-vlm/latest",
        "gpt://b1gfolder/gemma-3-27b-it",
        "gpt://b1gfolder/gemma-3-27b-it/latest",
    ]
