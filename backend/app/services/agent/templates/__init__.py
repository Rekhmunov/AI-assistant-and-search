"""Шаблоны агентов — специализированные промпты и приветствия."""

from app.services.agent.templates.reminder import REMINDER_SETUP_PROMPT, REMINDER_WELCOME

TEMPLATE_PROMPTS: dict[str, str] = {
    "reminder": REMINDER_SETUP_PROMPT,
}

TEMPLATE_WELCOMES: dict[str, str] = {
    "reminder": REMINDER_WELCOME,
}


def get_template_prompt(template: str | None) -> str | None:
    """Возвращает промпт для шаблона или None если шаблон не задан."""
    if not template:
        return None
    return TEMPLATE_PROMPTS.get(template)


def get_template_welcome(template: str | None) -> str | None:
    """Возвращает приветственное сообщение для шаблона или None."""
    if not template:
        return None
    return TEMPLATE_WELCOMES.get(template)
