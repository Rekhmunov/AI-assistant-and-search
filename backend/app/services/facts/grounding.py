"""Режимы grounding ответа: strict / hybrid / synthesis."""

from __future__ import annotations

import re
from typing import Literal

from app.services.facts.slots import STRICT_NUMERIC_SLOTS, SYNTHESIS_SLOTS

GroundingMode = Literal["strict", "hybrid", "synthesis"]

_VALID_GROUNDING: frozenset[str] = frozenset({"strict", "hybrid", "synthesis"})

_HYBRID_QUERY_RE = re.compile(
    r"(?:"
    r"напиш(?:и|ите)|сгенериру(?:й|йте)|состав(?:ь|ьте)|придумай|"
    r"отрефактор|рефактор|implement|write a |generate a |create a "
    r"|function|class\s|def\s|import\s|const\s|async\s|interface\s|"
    r"typescript|javascript|python|golang|\bgo\b|php|react|vue|rust|sql|docker|kubernetes|"
    r"\bapi\b|endpoint|regex|algorithm|"
    r"пост\s|стать[юя]|текст\s+для|лендинг|"
    r"код\s|скрипт|программ|алгоритм|debug|баг|ошибк[аи]\s+в\s+код"
    r")",
    re.I,
)


def normalize_grounding(raw: object) -> GroundingMode | None:
    if raw is None:
        return None
    g = str(raw).strip().lower()[:16]
    if g in _VALID_GROUNDING:
        return g  # type: ignore[return-value]
    return None


def is_hybrid_heuristic_query(query: str) -> bool:
    q = (query or "").strip()
    if not q or len(q) > 1200:
        return False
    if _HYBRID_QUERY_RE.search(q):
        return True
    if "```" in q:
        return True
    return False


def resolve_grounding_mode(
    *,
    fact_slots: list[str] | None,
    intent: str,
    rewriter_grounding: str | None = None,
    query: str = "",
) -> GroundingMode:
    """
    strict — цифры/даты только из источников [n].
    synthesis — план/how-to из материалов [n], без выдуманных метрик.
    hybrid — знания модели + поиск; [n] только на факты из сети.
    """
    slots = fact_slots or []
    if any(s in STRICT_NUMERIC_SLOTS for s in slots):
        return "strict"
    if "course_program" in slots or intent == "howto":
        return "synthesis"

    from_rewriter = normalize_grounding(rewriter_grounding)
    if from_rewriter == "strict":
        return "strict"
    if from_rewriter == "synthesis":
        return "synthesis"
    if from_rewriter == "hybrid":
        return "hybrid"

    if intent in ("compare_analyze", "document"):
        return "hybrid"
    if is_hybrid_heuristic_query(query):
        return "hybrid"

    return "strict"


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
