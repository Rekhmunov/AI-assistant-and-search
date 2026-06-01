"""Режимы grounding ответа: strict / hybrid / synthesis."""

from __future__ import annotations

from typing import Literal

from app.services.facts.slots import STRICT_NUMERIC_SLOTS, SYNTHESIS_SLOTS

GroundingMode = Literal["strict", "hybrid", "synthesis"]

_VALID_GROUNDING: frozenset[str] = frozenset({"strict", "hybrid", "synthesis"})


def normalize_grounding(raw: object) -> GroundingMode | None:
    if raw is None:
        return None
    g = str(raw).strip().lower()[:16]
    if g in _VALID_GROUNDING:
        return g  # type: ignore[return-value]
    return None


def resolve_grounding_mode(
    *,
    fact_slots: list[str] | None,
    intent: str,
    rewriter_grounding: str | None = None,
    query: str = "",
) -> GroundingMode:
    """
    Search Planner v2: grounding из rewriter; код только для жёстких слотов.
    strict — fx_rate, weather_now, company_financial.
    synthesis — course_program / howto.
    """
    _ = query  # сохранён для совместимости вызовов
    slots = fact_slots or []
    if any(s in STRICT_NUMERIC_SLOTS for s in slots):
        return "strict"
    if "course_program" in slots or intent == "howto":
        return "synthesis"

    from_rewriter = normalize_grounding(rewriter_grounding)
    if from_rewriter:
        return from_rewriter

    return "hybrid"


def adjust_grounding_for_retrieval(
    grounding: GroundingMode,
    *,
    weak_retrieval: bool,
    fact_slots: list[str] | None = None,
) -> GroundingMode:
    """Слабая выдача: не ужесточать — переключить на hybrid (кроме строгих слотов)."""
    slots = fact_slots or []
    if any(s in STRICT_NUMERIC_SLOTS for s in slots):
        return grounding
    if weak_retrieval and grounding == "strict":
        return "hybrid"
    return grounding


def effective_grounding_for_prompt(
    grounding: GroundingMode,
    fact_slots: list[str] | None,
    *,
    intent_howto: bool = False,
) -> GroundingMode:
    """Подсказки промпта: synthesis перекрывает hybrid при course/howto."""
    slots = fact_slots or []
    if any(s in STRICT_NUMERIC_SLOTS for s in slots):
        return "strict"
    if "course_program" in slots or intent_howto or grounding == "synthesis":
        return "synthesis"
    return grounding


def should_verify_answer_numbers(
    grounding: GroundingMode,
    fact_slots: list[str] | None,
) -> bool:
    if grounding != "strict":
        return False
    slots = fact_slots or []
    if any(s in SYNTHESIS_SLOTS for s in slots):
        return False
    return True
