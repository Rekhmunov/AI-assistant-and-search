"""Актуальный курс валют ЦБ РФ — без «списка сайтов»."""

import logging
from datetime import datetime, timezone

import httpx

from app.services.llm_provider import SearchSource

logger = logging.getLogger(__name__)

_CBR_JSON_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
_TIMEOUT = 8.0

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


def detect_currency_codes(query: str) -> list[str]:
    q = query.lower()
    found: list[str] = []
    for token, code in _CURRENCY_CODES.items():
        if token in q and code not in found:
            found.append(code)
    if not found and any(
        m in q
        for m in ("курс", "валют", "рубл", "обмен", "доллар", "евро", "usd", "eur")
    ):
        found.append("USD")
    return found[:3]


def is_currency_rate_query(query: str) -> bool:
    q = query.lower()
    if detect_currency_codes(q):
        return True
    return any(
        m in q
        for m in (
            "курс доллар",
            "курс евро",
            "курс usd",
            "курс eur",
            "курс валют",
            "доллар к руб",
            "usd/rub",
            "eur/rub",
            "сколько стоит доллар",
            "сколько стоит евро",
        )
    )


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
