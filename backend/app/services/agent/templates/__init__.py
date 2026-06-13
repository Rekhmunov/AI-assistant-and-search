"""Шаблоны агентов — специализированные промпты под каждый тип задачи."""

from app.services.agent.templates.reminder import REMINDER_SETUP_PROMPT

TEMPLATE_PROMPTS: dict[str, str] = {
    "reminder": REMINDER_SETUP_PROMPT,
}


def get_template_prompt(template: str | None) -> str | None:
    """Возвращает промпт для шаблона или None если шаблон не задан."""
    if not template:
        return None
    return TEMPLATE_PROMPTS.get(template)
