from app.services.agent.agent_reply_sanitize import (
    reply_looks_like_meta_instruction,
    sanitize_user_facing_reply,
)


def test_meta_instruction_detected():
    text = (
        "Пользователь спрашивает, как именно вы проверите доступ бота к группе. "
        "Вам нужно объяснить, каким инструментом вы проверите доступ. "
        "Пример ответа: «Я проверю доступ через maxprobechat. Ожидайте результат.»"
    )
    assert reply_looks_like_meta_instruction(text)
    assert sanitize_user_facing_reply(text) == ""


def test_normal_reply_passes():
    text = "Проверил группу: бот Glosix — администратор. Сообщение с курсом отправлено."
    assert not reply_looks_like_meta_instruction(text)
    assert sanitize_user_facing_reply(text) == text
