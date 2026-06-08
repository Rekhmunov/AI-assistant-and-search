"""Alice AI VLM: Responses API, auth, model URI candidates."""

from app.core.config import Settings
from app.services.alice_vlm import AliceVLMProvider


def test_alice_vlm_uses_responses_api_url():
    provider = AliceVLMProvider(Settings(yandex_folder_id="b1gfolder"))
    assert provider._responses_url() == "https://ai.api.cloud.yandex.net/v1/responses"


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
            yandex_vision_gemma_model="gemma-3-27b-it",
        )
    )
    assert provider._model_uri_candidates() == [
        "gpt://b1gfolder/aliceai-vlm/latest",
        "gpt://b1gfolder/aliceai-vlm",
        "gpt://b1gfolder/gemma-3-27b-it",
        "gpt://b1gfolder/gemma-3-27b-it/latest",
    ]


def test_alice_vlm_vision_input_uses_string_image_url():
    provider = AliceVLMProvider(Settings())
    input_messages = provider._vision_input(
        "что на фото?",
        [
            type("Img", (), {"media_type": "image/jpeg", "data_base64": "abc123"})(),  # type: ignore[arg-type]
        ],
        [],
    )
    content = input_messages[0]["content"]
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"] == "data:image/jpeg;base64,abc123"
    assert content[1]["type"] == "text"
    assert "что на фото?" in content[1]["text"]


def test_alice_vlm_text_from_responses_api():
    text = AliceVLMProvider._text_from_response(
        {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "На фото чайник."}],
                }
            ]
        }
    )
    assert text == "На фото чайник."


def test_alice_vlm_build_payload_uses_responses_fields():
    provider = AliceVLMProvider(Settings())
    payload = provider._build_payload(
        model_uri="gpt://f/gemma-3-27b-it",
        instructions="system",
        input_messages=[{"role": "user", "content": "hi"}],
        max_output_tokens=100,
        temperature=0.2,
        stream=True,
    )
    assert payload["model"] == "gpt://f/gemma-3-27b-it"
    assert payload["instructions"] == "system"
    assert payload["input"] == [{"role": "user", "content": "hi"}]
    assert payload["max_output_tokens"] == 100
    assert payload["stream"] is True
    assert "messages" not in payload
    assert "max_tokens" not in payload
