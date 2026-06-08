"""Alice AI VLM: Responses API, auth, model URI candidates."""

import base64
import io

from PIL import Image

from app.core.config import Settings
from app.services.alice_vlm import AliceVLMProvider, encode_vision_image_for_yandex


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
        "gpt://b1gfolder/gemma-3-27b-it",
        "gpt://b1gfolder/gemma-3-27b-it/latest",
    ]


def test_alice_vlm_vision_input_uses_responses_api_content_types():
    img = Image.new("RGB", (64, 64), color=(0, 128, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw_b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    provider = AliceVLMProvider(Settings())
    input_messages = provider._vision_input(
        "что на фото?",
        [
            type("Img", (), {"media_type": "image/jpeg", "data_base64": raw_b64})(),  # type: ignore[arg-type]
        ],
        [],
    )
    content = input_messages[0]["content"]
    assert content[0]["type"] == "input_image"
    assert str(content[0]["image_url"]).startswith("data:image/jpeg;base64,")
    assert content[1]["type"] == "input_text"
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


def test_encode_vision_image_resizes_to_jpeg():
    img = Image.new("RGB", (4000, 3000), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    raw_b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    data_uri = encode_vision_image_for_yandex(raw_b64, max_side=1536, max_bytes=900_000)
    assert data_uri.startswith("data:image/jpeg;base64,")
    out = base64.standard_b64decode(data_uri.split(",", 1)[1])
    out_img = Image.open(io.BytesIO(out))
    assert max(out_img.size) <= 1536


def test_alice_vlm_model_uri_candidates_alice_first_when_configured():
    provider = AliceVLMProvider(
        Settings(
            yandex_folder_id="b1gfolder",
            yandex_vision_alice_first=True,
        )
    )
    assert provider._model_uri_candidates()[0].endswith("/aliceai-vlm/latest")


def test_alice_vlm_stream_event_parsing():
    assert AliceVLMProvider._text_from_stream_event(
        {"type": "response.output_text.delta", "delta": "Привет"}
    ) == "Привет"
    assert AliceVLMProvider._text_from_stream_event(
        {"type": "response.output_text.done", "text": "Полный ответ"}
    ) == "Полный ответ"
    assert AliceVLMProvider._text_from_stream_event(
        {
            "type": "response.completed",
            "response": {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "Из completed"}],
                    }
                ]
            },
        }
    ) == "Из completed"


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
