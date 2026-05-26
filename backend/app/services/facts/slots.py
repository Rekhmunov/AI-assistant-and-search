"""Слоты структурированных фактов — из rewriter (контекст), не из ключевых слов."""

from __future__ import annotations

VALID_FACT_SLOTS = frozenset(
    {
        "fx_rate",
        "weather_now",
        "company_financial",
        "course_program",
    }
)


def normalize_fact_slots(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        slot = str(item).strip().lower()[:32]
        if slot in VALID_FACT_SLOTS and slot not in out:
            out.append(slot)
    return out


def resolve_fact_slots(rewriter_slots: list[str] | None) -> list[str]:
    """Единственный источник слотов для пайплайна — поле fact_slots от rewriter."""
    return normalize_fact_slots(rewriter_slots or [])


def ranking_flags_from_slots(fact_slots: list[str]) -> dict[str, bool]:
    return {
        "weather": "weather_now" in fact_slots,
        "currency": "fx_rate" in fact_slots,
        "course_program": "course_program" in fact_slots,
    }


# Цифры и даты в ответе должны совпадать с FactPack / источниками.
STRICT_NUMERIC_SLOTS = frozenset({"fx_rate", "weather_now", "company_financial"})

# План, шаги, рекомендации: структура из источников, без выдуманных ккал/курсов валют.
SYNTHESIS_SLOTS = frozenset({"course_program"})


def uses_strict_numeric_grounding(fact_slots: list[str] | None) -> bool:
    slots = fact_slots or []
    if any(s in STRICT_NUMERIC_SLOTS for s in slots):
        return True
    return not any(s in SYNTHESIS_SLOTS for s in slots)


def uses_synthesis_grounding(fact_slots: list[str] | None, *, intent_howto: bool = False) -> bool:
    slots = fact_slots or []
    if "course_program" in slots or intent_howto:
        return True
    if any(s in STRICT_NUMERIC_SLOTS for s in slots):
        return False
    return False
