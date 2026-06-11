"""Учёт затрат в группе MAX: категории, таблица, отчёт Excel."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance
from app.models.user import User
from app.services.agent.document_delivery import FileDeliveryResult
from app.services.agent.file_delivery import upload_bytes_to_max
from app.services.agent.profile import agent_config
from app.services.bot import MaxBotService
from app.services.doc_gen_schema import DocSection, DocTable, DocumentStructure
from app.services.xlsx_builder import build_xlsx_bytes

logger = logging.getLogger(__name__)

MAX_STORED_ENTRIES = 5000

_TRACKER_MARKERS = (
    "затрат",
    "таблиц",
    "категори",
    "excel",
    "exel",
    "xlsx",
    "сумм",
    "описан",
    "отчет",
    "отчёт",
    "фиксир",
    "учет",
    "учёт",
    "столбц",
)

_EXPENSE_LINE_RE = re.compile(
    r"^\s*(\d[\d\s]*)\s*\+\s*(.+)$",
    re.I,
)
_EXPENSE_LINE_SPACE_RE = re.compile(
    r"^\s*(\d[\d\s]{1,12})\s+(.{2,})$",
)

_REPORT_RE = re.compile(
    r"(?:отчет|отчёт|excel|exel|xlsx|таблиц)",
    re.I,
)


@dataclass
class ExpenseTrackerReply:
    text: str
    attachments: list[dict]
    handled: bool = True


def is_structured_group_tracker_task(text: str) -> bool:
    clean = (text or "").strip()
    if len(clean) < 40:
        return False
    low = clean.lower()
    if "групп" not in low and "чат" not in low:
        return False
    markers = sum(1 for marker in _TRACKER_MARKERS if marker in low)
    if markers >= 3:
        return True
    if "категори" in low and ("таблиц" in low or "excel" in low or "exel" in low):
        return True
    if ("буду писать" in low or "буду отправлять" in low) and ("сумм" in low or "затрат" in low):
        return True
    if "столбц" in low and "категори" in low:
        return True
    return False


def extract_expense_categories(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    head = re.split(
        r"в таблице должно|столбц[аы]?\s+долж|по запросу нужно",
        raw,
        maxsplit=1,
        flags=re.I,
    )[0]
    categories: list[str] = []
    seen: set[str] = set()
    for line in head.splitlines():
        line = line.strip(" •-\t")
        if not line or len(line) < 2:
            continue
        if re.match(r"^\d+[\).]", line):
            continue
        if re.search(r"формате|нужно будет|всего категор|я в эту группу|тебе нужно", line, re.I):
            continue
        name = line.split("(")[0].strip()
        if not name or len(name) > 80:
            continue
        if not re.match(r"^[A-Za-zА-Яа-яЁё0-9]", name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        categories.append(name)
    return categories[:50]


def agent_task_mode(agent: AgentInstance) -> str | None:
    cfg = agent_config(agent)
    mode = str(cfg.get("task_mode") or "").strip().lower()
    return mode or None


def expense_categories(agent: AgentInstance) -> list[str]:
    cfg = agent_config(agent)
    raw = cfg.get("expense_categories")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def parse_expense_line(text: str) -> tuple[int, str] | None:
    clean = (text or "").strip()
    if not clean or len(clean) > 500:
        return None
    if is_expense_report_request(clean):
        return None
    if re.search(r"категори|таблиц|отчет|отчёт|столбц", clean, re.I) and "+" not in clean:
        return None

    match = _EXPENSE_LINE_RE.match(clean)
    if match:
        amount_raw = match.group(1).replace(" ", "")
        desc = match.group(2).strip()
        if amount_raw.isdigit() and desc:
            return int(amount_raw), desc

    match = _EXPENSE_LINE_SPACE_RE.match(clean)
    if match:
        amount_raw = match.group(1).replace(" ", "")
        desc = match.group(2).strip()
        if amount_raw.isdigit() and desc and not desc[0].isdigit():
            return int(amount_raw), desc
    return None


def is_expense_report_request(text: str) -> bool:
    low = (text or "").lower()
    if not _REPORT_RE.search(low):
        return False
    return any(
        word in low
        for word in (
            "пришли",
            "пришлите",
            "отправ",
            "дай",
            "нужен",
            "нужно",
            "сделай",
            "сформируй",
            "покажи",
            "выгруз",
            "отчет",
            "отчёт",
        )
    )


def _parse_period(text: str) -> tuple[datetime | None, datetime | None]:
    low = (text or "").lower()
    now = datetime.now(timezone.utc)
    if any(word in low for word in ("сегодня", "за день")):
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if any(word in low for word in ("недел", "7 дней", "7дней")):
        return now - timedelta(days=7), now
    if any(word in low for word in ("месяц", "30 дней")):
        return now - timedelta(days=30), now
    if "все" in low or "весь" in low:
        return None, None
    return None, None


def _append_entry(agent: AgentInstance, entry: dict[str, Any]) -> None:
    cfg = dict(agent.config or {})
    rows = list(cfg.get("expense_entries") or [])
    rows.append(entry)
    cfg["expense_entries"] = rows[-MAX_STORED_ENTRIES:]
    agent.config = cfg


def _filter_entries(
    agent: AgentInstance,
    *,
    start: datetime | None,
    end: datetime | None,
) -> list[dict[str, Any]]:
    rows = list(agent_config(agent).get("expense_entries") or [])
    if not start and not end:
        return rows
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_at = row.get("at")
        if not raw_at:
            out.append(row)
            continue
        try:
            dt = datetime.fromisoformat(str(raw_at).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            out.append(row)
            continue
        if start and dt < start:
            continue
        if end and dt > end:
            continue
        out.append(row)
    return out


async def _categorize_expense(
    db: AsyncSession,
    redis_client,
    user: User,
    description: str,
    categories: list[str],
) -> tuple[str | None, str | None]:
    if not categories:
        return "Прочие затраты", None
    from app.services.providers.factory import resolve_runtime_providers

    llm, _, answer_model, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
    cats = "\n".join(f"- {name}" for name in categories)
    prompt = (
        f"Описание затраты: {description.strip()}\n\n"
        f"Категории:\n{cats}\n\n"
        "Верни JSON: {\"category\": \"точное имя категории из списка или null\", "
        "\"ask\": \"вопрос пользователю если неясно или пустая строка\"}"
    )
    try:
        raw = await llm.complete_text(
            [
                {
                    "role": "system",
                    "text": (
                        "Ты классифицируешь расходы. Выбирай категорию только из списка. "
                        "Если однозначно не подходит — ask с коротким вопросом на русском."
                    ),
                },
                {"role": "user", "text": prompt},
            ],
            model="pro" if answer_model == "pro" else "lite",
            max_tokens=200,
            temperature=0.1,
        )
    except Exception as exc:
        logger.warning("Expense categorize LLM failed: %s", exc)
        return None, "Не удалось определить категорию. Уточните, к какой категории отнести эту затрату?"

    import json

    data = None
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            data = None
    if not isinstance(data, dict):
        return None, "К какой категории отнести эту затрату?"

    ask = str(data.get("ask") or "").strip()
    category = str(data.get("category") or "").strip()
    if ask:
        return None, ask
    if category:
        for name in categories:
            if name.lower() == category.lower():
                return name, None
        for name in categories:
            if category.lower() in name.lower() or name.lower() in category.lower():
                return name, None
    return None, "К какой категории отнести эту затрату?"


async def _build_report_xlsx(
    agent: AgentInstance,
    entries: list[dict[str, Any]],
    *,
    period_label: str,
) -> bytes:
    rows = [
        [
            str(entry.get("category") or ""),
            str(entry.get("amount") or ""),
            str(entry.get("description") or ""),
        ]
        for entry in entries
    ]
    structure = DocumentStructure(
        title=f"Затраты — {period_label}",
        sections=[DocSection(heading="", paragraphs=[f"Записей: {len(rows)}"])],
        tables=[
            DocTable(
                caption="",
                headers=["Категория", "Сумма", "Описание"],
                rows=rows,
            )
        ],
    )
    return build_xlsx_bytes(structure)


async def handle_expense_tracker_reply(
    db: AsyncSession,
    redis_client,
    user: User,
    agent: AgentInstance,
    text: str,
    *,
    author: str = "",
    chat_id: int | None = None,
    bot: MaxBotService | None = None,
) -> ExpenseTrackerReply | None:
    if agent_task_mode(agent) != "expense_tracker":
        return None

    categories = expense_categories(agent)
    clean = (text or "").strip()
    if not clean:
        return None

    if is_expense_report_request(clean):
        start, end = _parse_period(clean)
        entries = _filter_entries(agent, start=start, end=end)
        if not entries:
            return ExpenseTrackerReply(
                text="За выбранный период затрат пока нет. Напишите расход в формате «Сумма + описание».",
                attachments=[],
            )
        period_label = "все записи"
        if start and end:
            period_label = f"{start.date().isoformat()} — {end.date().isoformat()}"
        xlsx = await _build_report_xlsx(agent, entries, period_label=period_label)
        _token, attachments = await upload_bytes_to_max(
            xlsx,
            f"zatraty_{datetime.now(timezone.utc).strftime('%Y%m%d')}.xlsx",
            bot=bot,
        )
        if not attachments:
            return ExpenseTrackerReply(
                text="Отчёт сформирован, но не удалось отправить файл в MAX.",
                attachments=[],
            )
        return ExpenseTrackerReply(
            text=f"Отчёт по затратам ({period_label}). Записей: {len(entries)}.",
            attachments=attachments,
        )

    parsed = parse_expense_line(clean)
    if not parsed:
        if len(clean) > 120 and is_structured_group_tracker_task(clean):
            return ExpenseTrackerReply(
                text=(
                    "Понял задачу учёта затрат. Пишите расходы в формате «Сумма + описание». "
                    "Для отчёта — «пришли отчёт в excel за неделю»."
                ),
                attachments=[],
            )
        return None

    amount, description = parsed
    category, question = await _categorize_expense(
        db, redis_client, user, description, categories
    )
    if question:
        return ExpenseTrackerReply(text=question, attachments=[])

    entry = {
        "category": category or "Прочие затраты",
        "amount": amount,
        "description": description,
        "at": datetime.now(timezone.utc).isoformat(),
        "author": author or "",
        "chat_id": chat_id,
    }
    _append_entry(agent, entry)
    return ExpenseTrackerReply(
        text=f"Записал: **{entry['category']}** — {amount} — {description}",
        attachments=[],
    )


def apply_expense_tracker_checklist(data: dict[str, Any], text: str) -> dict[str, Any]:
    if not is_structured_group_tracker_task(text):
        return data
    clean = text.strip()
    categories = extract_expense_categories(clean)
    data["role"] = "dm_assistant"
    data["scope"] = "group"
    data["interaction_mode"] = "support"
    data["support_instructions"] = clean[:4000]
    data["task_mode"] = "expense_tracker"
    data["output_format"] = "xlsx"
    if categories:
        data["expense_categories"] = categories
    if not data.get("reminder_message"):
        data["reminder_message"] = "Учёт затрат в группе: Сумма + описание"
    return data
