from app.services.image_gen_routing import image_generation_prompt, wants_image_generation


def test_wants_image_generation_positive():
    assert wants_image_generation("Нарисуй розового кота")
    assert wants_image_generation("Сгенерируй картинку заката над морем")
    assert wants_image_generation("Сделай изображение логотипа кофейни")
    assert wants_image_generation("картинка: горы зимой")


def test_wants_image_generation_negative():
    assert not wants_image_generation("Курс доллара сегодня")
    assert not wants_image_generation("Привет")
    assert not wants_image_generation("Расскажи про кота")


def test_image_generation_prompt_adds_draw():
    assert image_generation_prompt("закат").startswith("Нарисуй")


def test_image_generation_prompt_rewrites_sgeneriruy():
    assert image_generation_prompt("Сгенерируй план дома") == "Нарисуй план дома"
    assert image_generation_prompt("Сгенерируй картинку заката").startswith("Нарисуй")


def test_wants_image_generation_house_plan_short():
    assert wants_image_generation("Сгенерируй план дома")
