"""Шаблоны агентов — специализированные промпты, приветствия и названия."""

from app.services.agent.templates.reminder import REMINDER_SETUP_PROMPT, REMINDER_WELCOME
from app.services.agent.templates.secretary import SECRETARY_SETUP_PROMPT, SECRETARY_WELCOME
from app.services.agent.templates.assistant import ASSISTANT_SETUP_PROMPT, ASSISTANT_WELCOME

TEMPLATE_PROMPTS: dict[str, str] = {
    "reminder": REMINDER_SETUP_PROMPT,
    "secretary": SECRETARY_SETUP_PROMPT,
    "assistant": ASSISTANT_SETUP_PROMPT,
}

TEMPLATE_WELCOMES: dict[str, str] = {
    "reminder": REMINDER_WELCOME,
    "secretary": SECRETARY_WELCOME,
    "assistant": ASSISTANT_WELCOME,
}

# Название шаблона — используется как prefix в заголовке треда: «Напоминания 1»
TEMPLATE_TITLES: dict[str, str] = {
    "reminder": "Напоминания",
    "secretary": "Учет затрат",
    "assistant": "Личный ассистент",
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


def get_template_title(template: str | None) -> str | None:
    """Возвращает название шаблона для заголовка треда или None."""
    if not template:
        return None
    return TEMPLATE_TITLES.get(template)
