"""
Детерминированный движок агента-секретаря.
Работает по скомпилированным правилам (DSL) без LLM.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)


@dataclass
class ExecutorResult:
    text: str = ""
    file_instruction: str | None = None  # LLM-генерация (не используется для секретаря)
    file_format: str = "xlsx"
    xlsx_data: dict | None = None  # Прямая генерация xlsx без LLM
    handled: bool = True


def _get_rules(agent: AgentInstance) -> dict[str, Any] | None:
    cfg = dict(agent.config or {})
    rules = cfg.get("compiled_rules")
    if isinstance(rules, dict) and rules.get("version") == 1:
        return rules
    return None


def _get_pending(agent: AgentInstance) -> dict | None:
    return (agent.config or {}).get("secretary_pending")


def _set_pending(agent: AgentInstance, pending: dict | None) -> None:
    cfg = dict(agent.config or {})
    if pending is None:
        cfg.pop("secretary_pending", None)
    else:
        cfg["secretary_pending"] = pending
    agent.config = cfg


def _set_pending_period(agent: AgentInstance, period: str | None) -> None:
    cfg = dict(agent.config or {})
    if period is None:
        cfg.pop("secretary_pending_report", None)
    else:
        cfg["secretary_pending_report"] = period
    agent.config = cfg


def _get_pending_period(agent: AgentInstance) -> str | None:
    return (agent.config or {}).get("secretary_pending_report")


def _normalize(text: str) -> str:
    return text.strip().lower()


def _match_entity(token: str, entities: list[dict]) -> dict | None:
    """Находит сущность по токену в triggers. Учитывает длину (более специфичные сначала)."""
    token_low = _normalize(token)
    best: dict | None = None
    best_len = 0
    for entity in entities:
        for trigger in entity.get("triggers", []):
            t = _normalize(trigger)
            if t in token_low or token_low in t:
                if len(trigger) > best_len:
                    best = entity
                    best_len = len(trigger)
    return best


def _split_inline_entries(line: str) -> list[str]:
    """
    Разбивает строку вида '1000 ПЗР 2000 упаковка' на отдельные записи.
    Ищет границы: каждый новый числовой токен после текста начинает новую запись.
    """
    matches = list(_AMOUNT_RE.finditer(line))
    if len(matches) <= 1:
        return [line]

    parts: list[str] = []
    # Текст до первого числа (если есть) — прикрепляем к первой части
    pre = line[: matches[0].start()].strip()

    for i, m in enumerate(matches):
        chunk_start = m.start()
        chunk_end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
        chunk = line[chunk_start:chunk_end].strip()
        if i == 0 and pre:
            chunk = f"{pre} {chunk}"
        if chunk:
            parts.append(chunk)

    return parts if len(parts) > 1 else [line]


def _extract_lines(text: str) -> list[str]:
    """
    Разбивает текст на строки-записи.
    Поддерживает: \n, ;, а также несколько записей в одной строке ('1000 ПЗР 2000 упаковка').
    """
    raw_lines = [ln.strip() for ln in text.replace(";", "\n").split("\n") if ln.strip()]
    result: list[str] = []
    for line in raw_lines:
        result.extend(_split_inline_entries(line))
    return result


_AMOUNT_RE = re.compile(r"(\d[\d\s]*(?:[.,]\d+)?)")


def _parse_line(line: str) -> tuple[float | None, str]:
    """
    Парсит строку на (сумма, остаток).
    Поддерживает: "1000 ПЗР", "ПЗР 1000", "1 000 ПЗР", "1000,50 ПЗР".
    """
    m = _AMOUNT_RE.search(line)
    if not m:
        return None, line.strip()
    amount_str = m.group(1).replace(" ", "").replace(",", ".")
    try:
        amount = float(amount_str)
    except ValueError:
        return None, line.strip()
    rest = (line[: m.start()] + line[m.end() :]).strip()
    return amount, rest


def _is_confirmation(text: str) -> bool:
    low = _normalize(text)
    return low in {"да", "да.", "верно", "ок", "ok", "подтверждаю", "yes", "удали", "удалить"}


def _is_cancellation(text: str) -> bool:
    low = _normalize(text)
    return low in {"нет", "нет.", "отмена", "отменить", "cancel", "no"}


def _detect_command(text: str, rules: dict) -> str | None:
    """Возвращает имя команды если текст является командой."""
    low = _normalize(text)
    for cmd_name, cmd_cfg in rules.get("commands", {}).items():
        for trigger in cmd_cfg.get("triggers", []):
            if _normalize(trigger) in low:
                return cmd_name
    return None


def _parse_period(text: str, today: datetime) -> tuple[datetime, datetime] | None:
    """Парсит период из текста. Возвращает (start, end) или None."""
    low = _normalize(text)

    if "сегодня" in low or "today" in low:
        start = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end = today.replace(hour=23, minute=59, second=59)
        return start, end

    if "вчера" in low or "yesterday" in low:
        yesterday = today - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = yesterday.replace(hour=23, minute=59, second=59)
        return start, end

    if "неделю" in low or "за неделю" in low or "week" in low:
        start = (today - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = today.replace(hour=23, minute=59, second=59)
        return start, end

    if "месяц" in low or "за месяц" in low:
        start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = today.replace(hour=23, minute=59, second=59)
        return start, end

    # Диапазон "с DD.MM по DD.MM" или "DD.MM - DD.MM"
    range_m = re.search(r"(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?\s*[-–—по]+\s*(\d{1,2})[.\-/](\d{1,2})", low)
    if range_m:
        d1, m1 = int(range_m.group(1)), int(range_m.group(2))
        d2, m2 = int(range_m.group(4)), int(range_m.group(5))
        yr = today.year
        try:
            start = datetime(yr, m1, d1, 0, 0, 0, tzinfo=timezone.utc)
            end = datetime(yr, m2, d2, 23, 59, 59, tzinfo=timezone.utc)
            return start, end
        except ValueError:
            pass

    # Одна дата "DD.MM" или "DD.MM.YYYY"
    single_m = re.search(r"(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?", low)
    if single_m:
        d, m = int(single_m.group(1)), int(single_m.group(2))
        yr_str = single_m.group(3)
        yr = int(yr_str) if yr_str else today.year
        if yr < 100:
            yr += 2000
        try:
            day_start = datetime(yr, m, d, 0, 0, 0, tzinfo=timezone.utc)
            day_end = datetime(yr, m, d, 23, 59, 59, tzinfo=timezone.utc)
            return day_start, day_end
        except ValueError:
            pass

    return None


def _filter_records_by_period(
    records: list[dict],
    start: datetime,
    end: datetime,
) -> list[dict]:
    filtered = []
    for r in records:
        at_str = r.get("at", "")
        try:
            at = datetime.fromisoformat(at_str)
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            if start <= at <= end:
                filtered.append(r)
        except Exception:
            pass
    return filtered


def _format_period_label(start: datetime, end: datetime) -> str:
    if start.date() == end.date():
        return start.strftime("%d.%m.%Y")
    return f"{start.strftime('%d.%m.%Y')} – {end.strftime('%d.%m.%Y')}"


async def execute_secretary_message(
    db: AsyncSession,
    agent: AgentInstance,
    bot: MaxBotService,
    chat_id: int,
    text: str,
    author: str,
) -> ExecutorResult | None:
    """
    Обрабатывает входящее сообщение детерминированно по compiled_rules.
    Возвращает ExecutorResult или None если правил нет / сообщение не распознано.
    """
    rules = _get_rules(agent)
    if not rules:
        return None

    from app.services.agent.agent_records import store_record, query_records, delete_record

    entities: list[dict] = rules.get("entities", [])
    responses: dict = rules.get("responses", {})
    commands: dict = rules.get("commands", {})
    today = datetime.now(timezone.utc)

    # ─── 1. Обработка pending: подтверждение удаления ────────────────────────
    pending = _get_pending(agent)
    if pending and pending.get("type") == "delete_confirm":
        if _is_confirmation(text):
            delete_record(agent, "records", last=True)
            _set_pending(agent, None)
            return ExecutorResult(text="✅ Запись удалена")
        elif _is_cancellation(text):
            _set_pending(agent, None)
            return ExecutorResult(text="Отменено, запись сохранена")
        # Не подтверждение и не отмена — очищаем pending, обрабатываем как новое сообщение
        _set_pending(agent, None)

    # ─── 2. Обработка pending: уточнение категории (поддержка очереди) ─────────
    if pending and pending.get("type") == "clarify_entity":
        # Поддерживаем и старый формат (amount/token) и новый (queue)
        queue: list[dict] = pending.get("queue", [])
        if not queue:
            queue = [{"amount": pending.get("amount"), "token": pending.get("token", "")}]

        current = queue[0]
        amount = current.get("amount")
        raw_token = current.get("token", "")

        entity = _match_entity(text, entities)
        if entity:
            # Обучение: запоминаем новый триггер
            for e in entities:
                if e["name"] == entity["name"]:
                    t = _normalize(text.strip())
                    if t and t not in e.get("triggers", []):
                        e.setdefault("triggers", []).append(t)
                        cfg = dict(agent.config or {})
                        cfg["compiled_rules"] = rules
                        agent.config = cfg
                    break

            store_record(agent, "records", {
                "category": entity["name"],
                "amount": amount,
                "note": raw_token,
                "author": author,
                "chat_id": chat_id,
            })
            confirm = responses.get("on_success", "✅ Записано в категорию: {category}")
            amt_str = str(int(amount)) if amount == int(amount) else str(amount)
            result_text = confirm.format(amount=amt_str, category=entity["name"])

            # Остаток очереди
            remaining = queue[1:]
            if remaining:
                _set_pending(agent, {"type": "clarify_entity", "queue": remaining})
                next_item = remaining[0]
                next_amt = next_item.get("amount")
                next_token = next_item.get("token", "")
                next_amt_str = str(int(next_amt)) if next_amt == int(next_amt) else str(next_amt)
                unknown_msg = responses.get("on_unknown_entity", "❓ Не распознана категория '{token}'. Уточните:")
                clarify_text = unknown_msg.format(token=next_token[:50])
                return ExecutorResult(text=f"{result_text}\n{clarify_text} (сумма: {next_amt_str})")
            else:
                _set_pending(agent, None)
                return ExecutorResult(text=result_text)
        else:
            return ExecutorResult(
                text=f"❓ Не нашёл подходящую категорию для «{text.strip()}». "
                     f"Пожалуйста, уточните категорию из списка."
            )

    # ─── 3. Обработка pending: период отчёта ─────────────────────────────────
    pending_report = _get_pending_period(agent)
    if pending_report:
        period = _parse_period(text, today)
        if period:
            start, end = period
            _set_pending_period(agent, None)
            label = _format_period_label(start, end)
            records = query_records(agent, "records")
            filtered = _filter_records_by_period(records, start, end)
            if not filtered:
                return ExecutorResult(text=f"За период {label} записей не найдено.")
            columns = commands.get("report", {}).get("columns", ["Категория", "Затрата", "Примечание"])
            title = commands.get("report", {}).get("title_template", "Отчёт за {period}").format(period=label)
            return ExecutorResult(
                text=f"Отчёт за {label} — {len(filtered)} записей:",
                xlsx_data={"title": title, "columns": columns, "records": filtered},
            )
        else:
            return ExecutorResult(
                text="Не распознал период. Укажите, например: «сегодня», «14.06», «с 10.06 по 14.06», «за неделю»"
            )

    # ─── 4. Определение команды ───────────────────────────────────────────────
    cmd = _detect_command(text, rules)

    if cmd == "report":
        period = _parse_period(text, today)
        if period:
            start, end = period
            label = _format_period_label(start, end)
            records = query_records(agent, "records")
            filtered = _filter_records_by_period(records, start, end)
            if not filtered:
                return ExecutorResult(text=f"За период {label} записей не найдено.")
            columns = commands.get("report", {}).get("columns", ["Категория", "Затрата", "Примечание"])
            title = commands.get("report", {}).get("title_template", "Отчёт за {period}").format(period=label)
            return ExecutorResult(
                text=f"Отчёт за {label} — {len(filtered)} записей:",
                xlsx_data={"title": title, "columns": columns, "records": filtered},
            )
        else:
            period_q = commands.get("report", {}).get("period_question", "За какой период нужен отчёт?")
            _set_pending_period(agent, "pending")
            return ExecutorResult(text=f"❓ {period_q}")

    if cmd == "show_records":
        limit = commands.get("show_records", {}).get("limit", 20)
        records = query_records(agent, "records", limit=limit)
        if not records:
            return ExecutorResult(text="База пуста — записей нет.")
        lines = []
        for r in records[-limit:]:
            at = r.get("at", "")[:10]
            cat = r.get("category", "?")
            amt = r.get("amount", "?")
            note = r.get("note", "")
            lines.append(f"• {at} {cat} — {amt}" + (f" ({note})" if note else ""))
        return ExecutorResult(text="\n".join(lines))

    if cmd == "delete":
        records = query_records(agent, "records", limit=1)
        if not records:
            return ExecutorResult(text="Нет записей для удаления.")
        last = records[-1]
        desc = f"{last.get('category', '?')}, {last.get('amount', '?')}, {last.get('at', '')[:10]}"
        _set_pending(agent, {"type": "delete_confirm", "record": last})
        return ExecutorResult(text=f"❓ Удалить эту запись? {desc}. Напишите «да» для подтверждения.")

    # ─── 5. Запись данных ─────────────────────────────────────────────────────
    lines = _extract_lines(text)
    if not lines:
        return None

    results: list[str] = []
    clarify_queue: list[dict] = []  # Записи с непонятной категорией — очередь уточнения

    for line in lines:
        amount, rest = _parse_line(line)

        if amount is None:
            # Строка без суммы — пропускаем если есть другие, иначе сообщаем
            if not results and not clarify_queue:
                no_amount_msg = responses.get(
                    "on_missing_amount",
                    "Для корректной записи нужно указать сумму и категорию затраты",
                )
                return ExecutorResult(text=no_amount_msg)
            continue

        entity = _match_entity(rest, entities) if rest else None

        if entity is None and rest:
            # Категория не распознана — добавляем в очередь уточнения
            clarify_queue.append({"amount": amount, "token": rest})
            continue

        if entity is None:
            clarify_queue.append({"amount": amount, "token": rest or "?"})
            continue

        # Нужно уточнение варианта (например белая/серая стежка)
        if entity.get("require_clarification") and entity.get("clarification_options"):
            options = "/".join(entity["clarification_options"])
            q = entity.get("clarification_question") or f"Уточните вариант для «{entity['name']}»:"
            clarify_queue.append({"amount": amount, "token": rest})
            continue

        store_record(agent, "records", {
            "category": entity["name"],
            "amount": amount,
            "note": rest,
            "author": author,
            "chat_id": chat_id,
        })
        confirm = responses.get("on_success", "✅ Записано в категорию: {category}")
        amt_str = str(int(amount)) if amount == int(amount) else str(amount)
        results.append(confirm.format(amount=amt_str, category=entity["name"]))

    # Если есть записи требующие уточнения — сохраняем очередь и спрашиваем первую
    if clarify_queue:
        _set_pending(agent, {"type": "clarify_entity", "queue": clarify_queue})
        first = clarify_queue[0]
        amt = first["amount"]
        token = first["token"]
        amt_str = str(int(amt)) if amt == int(amt) else str(amt)
        unknown_msg = responses.get("on_unknown_entity", "❓ Не распознана категория '{token}'. Уточните:")
        clarify_text = unknown_msg.format(token=token[:50]) + f" (сумма: {amt_str})"

        if results:
            # Часть записана, часть требует уточнения
            confirmed = "\n".join(results)
            return ExecutorResult(text=f"{confirmed}\n{clarify_text}")
        else:
            return ExecutorResult(text=clarify_text)

    if not results:
        return None

    if len(results) == 1:
        return ExecutorResult(text=results[0])

    multi_msg = responses.get("on_multi_record", "✅ Записано {count} позиций")
    summary = multi_msg.format(count=len(results)) + ":\n" + "\n".join(results)
    return ExecutorResult(text=summary)
