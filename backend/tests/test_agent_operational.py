from app.services.agent.intent_hints import infer_role_from_text
from app.services.agent.operational import is_operational_max_query, user_wants_admin_check


def test_admin_check_is_operational():
    text = "Вот группа https://web.max.ru/-75602062003657\nПроверь, ты там админ?"
    assert user_wants_admin_check(text)
    assert is_operational_max_query(text)


def test_operational_does_not_infer_group_reminder_role():
    text = "Вот группа https://web.max.ru/-75602062003657\nПроверь, ты там админ?"
    assert infer_role_from_text(text) is None
