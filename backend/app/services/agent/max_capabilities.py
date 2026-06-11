"""Каталог возможностей MAX и Glosix для автономного агента."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentCapability:
    tool: str
    category: str
    description: str
    destructive: bool = False


CAPABILITIES: tuple[AgentCapability, ...] = (
    AgentCapability("max_probe_chat", "max", "Проверить доступ бота к чату/каналу MAX"),
    AgentCapability("max_get_chat", "max", "Информация о чате MAX"),
    AgentCapability("max_list_bot_chats", "max", "Список чатов, куда добавлен бот"),
    AgentCapability("max_resolve_channel_link", "max", "Получить chat_id по ссылке max.ru"),
    AgentCapability("max_send_test", "max", "Отправить тестовое текстовое сообщение", destructive=True),
    AgentCapability("max_send_message", "max", "Отправить текст в MAX (личка или группа)", destructive=True),
    AgentCapability("max_send_file", "max", "Сгенерировать и отправить файл (docx/pdf/xlsx/image)", destructive=True),
    AgentCapability("max_read_activity_logs", "max", "Журнал dispatch агента за 24ч"),
    AgentCapability("web_search", "glosix", "Полный поиск Glosix: ответ по источникам из интернета"),
    AgentCapability("read_thread_summary", "memory", "Последние сообщения треда настройки в Glosix"),
    AgentCapability("search_thread_history", "memory", "Поиск по всей истории треда Glosix"),
    AgentCapability("store_agent_record", "memory", "Сохранить запись в таблицу агента (затраты, события)"),
    AgentCapability("query_agent_records", "memory", "Выбрать записи из таблицы агента"),
    AgentCapability("update_agent_memory", "memory", "Добавить стабильный факт в память агента"),
)

CAPABILITY_BY_TOOL = {c.tool: c for c in CAPABILITIES}


def tools_appendix_for_mode(*, runtime: bool = False) -> str:
    lines = [
        "Доступные инструменты (только из списка):",
    ]
    for cap in CAPABILITIES:
        mark = " [осторожно]" if cap.destructive else ""
        lines.append(f"- {cap.tool} — {cap.description}{mark}")
    if runtime:
        lines.append(
            "\nРежим MAX: отвечай пользователю в мессенджере. "
            "Для затрат — store_agent_record; для отчётов — query_agent_records + max_send_file."
        )
    else:
        lines.append(
            "\nРежим Glosix-треда: по умолчанию помогай и проверяй через tools. "
            "checklist заполняй только для явной настройки автоматизации. "
            "Вопросы про админа/доступ/чаты → max_probe_chat, max_get_chat, max_list_bot_chats, search_thread_history. "
            "Для актуальных данных из интернета — web_search; доставку в MAX собирай сам из tools (max_send_message, max_send_file и др.)."
        )
    lines.append(
        '\nФормат JSON: {"reply": "...", "done": true/false, '
        '"tool_calls": [{"tool": "...", "arguments": {}}], '
        '"checklist": {...}, "ready_for_confirmation": false, "activate": false}'
    )
    if runtime:
        lines[-1] = (
            '\nФормат JSON: {"reply": "...", "done": true/false, '
            '"tool_calls": [{"tool": "...", "arguments": {}}]}'
        )
    return "\n".join(lines)
