"""Актуальный курс валют ЦБ РФ — без «списка сайтов»."""

import logging
import re
from datetime import datetime, timezone

import httpx

from app.services.llm_provider import SearchSource

logger = logging.getLogger(__name__)

_CBR_JSON_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
_TIMEOUT = 8.0

# «Курс» = программа обучения / похудения, не валюта
_COURSE_PROGRAM_RE = re.compile(
    r"курс\s+(?:на|по|для)\s+|"
    r"(?:распиш|составь|опиши|расскажи)\s+.{0,40}курс|"
    r"курс\s+.{0,30}(?:похуден|обучен|трениров|марафон|программ|урок|интенсив|"
    r"репетитор|экзамен|английск|python|программир|нутрициолог|диетолог)",
    re.I,
)

_COURSE_TOPIC_MARKERS = (
    "похуден",
    "обучен",
    "трениров",
    "марафон",
    "интенсив",
    "урок",
    "лекци",
    "репетитор",
    "нутрициолог",
    "диетолог",
    "план питания",
    "программ похуд",
)

_FX_EXPLICIT_PHRASES = (
    "курс доллар",
    "курс евро",
    "курс usd",
    "курс eur",
    "курс валют",
    "курс юан",
    "курс фунт",
    "доллар к руб",
    "евро к руб",
    "usd/rub",
    "eur/rub",
    "сколько стоит доллар",
    "сколько стоит евро",
    "курс цб",
    "курс центробанк",
)

_CURRENCY_CODES = {
    "доллар": "USD",
    "доллара": "USD",
    "доллару": "USD",
    "usd": "USD",
    "бакс": "USD",
    "евро": "EUR",
    "eur": "EUR",
    "юань": "CNY",
    "cny": "CNY",
    "фунт": "GBP",
    "gbp": "GBP",
    "иена": "JPY",
    "jpy": "JPY",
    "тенге": "KZT",
    "kzt": "KZT",
}


def is_course_program_query(query: str) -> bool:
    """Курс как программа/обучение, не биржевой курс."""
    q = query.strip().lower()
    if _COURSE_PROGRAM_RE.search(q):
        return True
    if "курс" in q and any(m in q for m in _COURSE_TOPIC_MARKERS):
        return True
    return False


def detect_currency_codes(query: str) -> list[str]:
    q = query.lower()
    if is_course_program_query(q):
        return []
    found: list[str] = []
    for token, code in _CURRENCY_CODES.items():
        if token in q and code not in found:
            found.append(code)
    if not found and any(p in q for p in _FX_EXPLICIT_PHRASES):
        found.append("USD")
    return found[:3]


def is_currency_rate_query(query: str) -> bool:
    q = query.lower()
    if is_course_program_query(q):
        return False
    if any(token in q for token in _CURRENCY_CODES):
        return True
    if any(p in q for p in _FX_EXPLICIT_PHRASES):
        return True
    if "курс" in q and any(m in q for m in ("валют", "рубл", "обмен", "цб", "центробанк", "cbr")):
        return True
    return False


async def fetch_cbr_rates(codes: list[str] | None = None) -> tuple[str, str] | None:
    """
    Возвращает (текст_фактов, дата_курса) или None при ошибке.
    Источник: официальные данные ЦБ (зеркало daily_json).
    """
    codes = codes or ["USD"]
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(_CBR_JSON_URL)
            response.raise_for_status()
            data = response.json()
    except Exception:
        logger.warning("CBR rates fetch failed", exc_info=True)
        return None

    valutes = data.get("Valute") or {}
    date_raw = str(data.get("Date") or "")
    lines: list[str] = []

    for code in codes:
        block = valutes.get(code)
        if not block:
            continue
        name = block.get("Name") or code
        value = float(block.get("Value") or 0)
        nominal = int(block.get("Nominal") or 1)
        per_one = value / nominal if nominal else value
        lines.append(f"{name} ({code}): {per_one:.4f} ₽ за 1 {code}")

    if not lines:
        return None

    date_label = date_raw or datetime.now(timezone.utc).strftime("%d.%m.%Y")
    text = (
        f"Официальный курс Банка России на {date_label}:\n"
        + "\n".join(lines)
        + "\nИсточник: cbr.ru"
    )
    return text, date_label


def cbr_source_from_facts(facts: str, *, index: int = 1) -> SearchSource:
    return SearchSource(
        index=index,
        url="https://www.cbr.ru/currency_base/daily/",
        title="Курс ЦБ РФ",
        snippet=facts[:3200],
        domain="cbr.ru",
    )
