from app.services.thread_context import llm_history_for_turn


def test_llm_history_for_turn_clears_on_new_attachment():
    history = [
        ("user", "что на фото"),
        ("assistant", "На фото девушка на кровати."),
    ]
    assert llm_history_for_turn(history, has_attachments=True) == []


def test_llm_history_for_turn_keeps_without_attachment():
    history = [
        ("user", "привет"),
        ("assistant", "Здравствуйте"),
    ]
    assert llm_history_for_turn(history, has_attachments=False) == history
