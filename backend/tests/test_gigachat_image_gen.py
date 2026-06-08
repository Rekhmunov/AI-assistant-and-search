from app.services.gigachat_image_gen import _clean_assistant_text, _extract_file_id, _image_gen_payload

SAMPLE = (
    'Запускаю генерацию изображения. '
    '<img src="b28fbd4f-105a-43e0-ba5a-2faa80b1f43c" fuse="true"/> '
    "— вот розовый кот, который у меня получился."
)


def test_extract_file_id_from_gigachat_img_tag():
    assert _extract_file_id(SAMPLE) == "b28fbd4f-105a-43e0-ba5a-2faa80b1f43c"


def test_clean_assistant_text_removes_full_img_tag():
    cleaned = _clean_assistant_text(SAMPLE)
    assert "fuse=" not in cleaned
    assert "<img" not in cleaned
    assert "розовый кот" in cleaned


def test_clean_orphan_fuse_fragment():
    broken = ' fuse="true"/> сгенерировал фото кота.'
    cleaned = _clean_assistant_text(broken)
    assert cleaned == "сгенерировал фото кота."


def test_extract_bare_uuid():
    uid = "b28fbd4f-105a-43e0-ba5a-2faa80b1f43c"
    assert _extract_file_id(f"Готово: {uid}") == uid


def test_image_gen_payload_matches_gigachat_docs():
    payload = _image_gen_payload("Нарисуй кота", "GigaChat-2-Pro", stream=False)
    assert payload["function_call"] == "auto"
    assert "functions" not in payload
    assert payload["messages"][0]["content"] == "Нарисуй кота"
