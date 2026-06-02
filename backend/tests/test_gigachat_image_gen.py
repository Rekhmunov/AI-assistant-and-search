from app.services.gigachat_image_gen import _clean_assistant_text, _extract_file_id

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
