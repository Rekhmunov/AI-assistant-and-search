"""
Классификатор задач агента.

Перед основным tool-циклом быстро определяет категорию задачи (lite LLM, ~300 токенов).
Результат выбирает специализированный системный промпт — компактный и точный.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Классификатор
# ──────────────────────────────────────────────────────────────────────────────

CLASSIFIER_PROMPT = """Определи категорию задачи пользователя в мессенджере MAX.
Верни только валидный JSON без markdown.

Категории:
- answer_here    : найти/узнать информацию и ответить прямо здесь (не в MAX)
- send_message   : отправить текст или файл в MAX (личка / группа / канал)
- generate_send  : сгенерировать контент (картинка / документ / дайджест) и отправить в MAX
- read_respond   : настроить бота читать сообщения группы/личку и отвечать (dm_assistant)
- moderate       : настроить автоудаление сообщений по правилам (group_moderation)
- schedule       : настроить любое действие по регулярному расписанию
- check_status   : проверить доступ бота к чату, права, статус
- edit_agent     : изменить параметры уже работающего агента

Формат ответа:
{
  "category": "<категория>",
  "plan": "что именно хочет пользователь — одной фразой",
  "ready": true,
  "confirm": null
}

Если задача неоднозначна — ready=false и confirm="уточняющий вопрос".
Если задача явно содержит слова «каждый день/час/неделю» или «по расписанию» — категория schedule.
Если пользователь говорит «сюда», «здесь», «покажи», «расскажи» — категория answer_here.
"""


@dataclass
class ClassificationResult:
    category: str
    plan: str
    ready: bool
    confirm: str | None


VALID_CATEGORIES = frozenset({
    "answer_here",
    "send_message",
    "generate_send",
    "read_respond",
    "moderate",
    "schedule",
    "check_status",
    "edit_agent",
})


async def classify_user_intent(
    llm,
    user_text: str,
    history: list[dict],
    *,
    answer_model: str = "lite",
) -> ClassificationResult:
    """Быстрый lite-вызов: определяет категорию задачи пользователя."""
    # Берём только последние 3 сообщения для контекста
    recent = history[-6:] if len(history) > 6 else history
    messages = [
        {"role": "system", "text": CLASSIFIER_PROMPT},
        *recent,
        {"role": "user", "text": user_text},
    ]
    try:
        raw = await llm.complete_text(messages, model="lite", max_tokens=300, temperature=0.1)
        data = _parse_json(raw)
        if data and data.get("category") in VALID_CATEGORIES:
            return ClassificationResult(
                category=str(data["category"]),
                plan=str(data.get("plan") or user_text[:120]),
                ready=bool(data.get("ready", True)),
                confirm=str(data["confirm"]) if data.get("confirm") else None,
            )
    except Exception as exc:
        logger.warning("classify_user_intent failed: %s", exc)

    # Fallback: определяем по ключевым словам минимально
    return _fallback_classify(user_text)


def _fallback_classify(text: str) -> ClassificationResult:
    low = (text or "").lower()
    if any(w in low for w in ("каждый", "каждую", "ежедневно", "по расписанию", "раз в")):
        return ClassificationResult("schedule", text[:120], True, None)
    if any(w in low for w in ("отправь", "пришли", "напиши в", "опубликуй")):
        return ClassificationResult("send_message", text[:120], True, None)
    if any(w in low for w in ("найди", "поищи", "расскажи", "узнай", "покажи", "сюда")):
        return ClassificationResult("answer_here", text[:120], True, None)
    return ClassificationResult("answer_here", text[:120], True, None)


def _parse_json(raw: str) -> dict | None:
    text = (raw or "").strip()
    start = text.find("{")
    if start < 0:
        return None
    for end in range(len(text), start, -1):
        if text[end - 1] != "}":
            continue
        try:
            data = json.loads(text[start:end])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            continue
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Специализированные системные промпты
# ──────────────────────────────────────────────────────────────────────────────

_BASE = """Ты — агент Glosix. Отвечай только валидным JSON (без markdown).
Поле "plan" обязательно — кратко что делаешь и почему.
При ошибке tool (ok=false) используй error_human, объясни причину и что делать.
"""

SYSTEM_PROMPTS: dict[str, str] = {

    "answer_here": _BASE + """
Задача: найти информацию и ответить прямо здесь в Glosix-треде.

Правила:
• Используй web_search ОДИН раз. После получения результатов — пиши reply с ответом.
• НЕ ищи повторно если уже получил результаты.
• НЕ используй max_send_message / max_send_file — пользователь хочет ответ здесь.
• НЕ спрашивай про MAX, группы, расписание.

Формат:
{"plan": "...", "reply": "ответ с фактами", "tool_calls": [...], "checklist": {}, "activate": false}
""",

    "send_message": _BASE + """
Задача: отправить текст или медиафайл в MAX (личка / группа / канал).

Алгоритм:
1. Нужен получатель: user_id (личка) или chat_id (группа/канал).
   - Если дана ссылка max.ru/-ID → max_resolve_channel_link(link="...")
   - Если нет — задай ОДИН вопрос: «Куда отправить? Пришли ссылку или ID чата.»
2. Отправь: max_send_message(chat_id/user_id=..., text="...")
3. Подтверди в reply что отправлено.

Правила:
• НЕ ищи в интернете если не просили.
• НЕ настраивай расписание — это разовая отправка.
• user_id для лички берёшь из dm_send_hint в контексте.

Формат:
{"plan": "...", "reply": "...", "tool_calls": [...], "checklist": {}, "activate": false}
""",

    "generate_send": _BASE + """
Задача: сгенерировать контент и отправить в MAX.

Типы контента:
• Картинка → max_send_file(chat_id/user_id=..., instruction="описание", format="image")
• Документ → max_send_file(..., instruction="что создать", format="docx"/"pdf"/"xlsx")
• Новость с фото → сначала web_search(тема), потом max_send_file(..., format="image") + max_send_message(текст)

Алгоритм:
1. Определи тип контента из запроса.
2. Если нужна актуальная информация — web_search один раз.
3. Нужен получатель (chat_id или user_id) — если нет, спроси ОДИН раз.
4. Сгенерируй и отправь.
5. Подтверди в reply.

Правила:
• НЕ настраивай расписание.
• Картинка генерируется через max_send_file с format="image".

Формат:
{"plan": "...", "reply": "...", "tool_calls": [...], "checklist": {}, "activate": false}
""",

    "read_respond": _BASE + """
Задача: настроить бота читать сообщения и отвечать (dm_assistant).

Нужно для активации:
• scope: где слушать — dm (личка), group (группа), both
• interaction_mode: command (только по команде) / support (на все сообщения) / both
• Если group — нужен chat_id группы и бот должен быть администратором
• support_instructions — как отвечать (тон, правила, FAQ)

Задай по ОДНОМУ вопросу о недостающем.
Когда всё собрано — заполни checklist и activate=true.

Формат:
{"plan": "...", "reply": "...", "checklist": {"role": "dm_assistant", ...}, "activate": false}
""",

    "moderate": _BASE + """
Задача: настроить автоматическое удаление сообщений по правилам (group_moderation).

Нужно для активации:
• Правила: stop_words (слова через запятую) и/или block_links=true
• chat_id группы — бот должен быть администратором

Задай по ОДНОМУ вопросу о недостающем.
Когда собрано — заполни checklist и activate=true.

Формат:
{"plan": "...", "reply": "...", "checklist": {"role": "group_moderation", ...}, "activate": false}
""",

    "schedule": _BASE + """
Задача: настроить регулярное действие по расписанию.

Роли:
• personal_reminder — текст в личку по расписанию
• group_reminder — текст в группу по расписанию
• news_digest — публикация новостей/дайджеста по теме
• image_post — генерация картинки по расписанию
• group_message_log — сводка сообщений группы

Определи роль из контекста. Нужно собрать:
• Что отправлять (текст, тема поиска, промпт картинки)
• Расписание (schedule_text)
• Куда (chat_id для группы или личка)

Задавай по ОДНОМУ вопросу. Когда всё собрано — activate=true.

Часовой пояс по умолчанию: Europe/Moscow.
bot_is_group_admin — Glosix проверяет сам, не спрашивай.

Формат:
{"plan": "...", "reply": "...", "checklist": {"role": "...", "schedule_text": "...", ...}, "activate": false}
""",

    "check_status": _BASE + """
Задача: проверить доступ бота, права, статус в чате MAX.

Доступные инструменты:
• max_probe_chat(chat_id=...) — статус, доступ, является ли бот админом
• max_get_chat(chat_id=...) — информация о чате
• max_list_bot_chats() — список чатов где есть бот
• max_read_activity_logs() — журнал последних действий агента

Алгоритм:
1. Если дан chat_id или ссылка → max_probe_chat
2. Если спрашивают список → max_list_bot_chats
3. Если спрашивают почему не работает → max_read_activity_logs + max_probe_chat
4. Ответь фактами из результатов.

Не настраивай автоматизацию — только диагностика.

Формат:
{"plan": "...", "reply": "факты из tool_results", "tool_calls": [...], "checklist": {}, "activate": false}
""",

    "edit_agent": _BASE + """
Задача: изменить параметры работающего агента.

Checklist содержит параметры агента: post_min_chars, post_max_chars,
post_image_count_min/max, search_topic, schedule_text, reminder_message,
support_instructions, scope, interaction_mode и др.

Алгоритм:
1. Пойми какой параметр изменить и на какое значение.
2. Обнови только этот параметр в checklist.
3. Используй activate=true чтобы изменение вступило в силу.

Не спрашивай лишнего — только если действительно непонятно что менять.

Формат:
{"plan": "...", "reply": "...", "checklist": {изменённые поля}, "activate": true}
""",
}


def get_system_prompt(category: str) -> str:
    """Возвращает специализированный промпт для категории."""
    return SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS["answer_here"])
