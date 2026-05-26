"""Извлечение фактов из источников через YandexGPT (JSON)."""

import json
import logging
import re

from typing import TYPE_CHECKING

from app.services.facts.models import Fact, FactPack
from app.services.llm_provider import SearchSource
from app.services.prompts.defaults import (
    EXTRACT_COURSE_ADDON,
    EXTRACT_FINANCIAL_ADDON,
    EXTRACT_SYSTEM,
    EXTRACT_USER,
)

if TYPE_CHECKING:
    from app.services.providers.factory import ChatLLM

logger = logging.getLogger(__name__)


def _format_sources_block(sources: list[SearchSource], max_per: int = 4500) -> str:
    lines: list[str] = []
    for s in sources[:8]:
        snippet = (s.snippet or "")[:max_per]
        lines.append(f'[{s.index}] {s.domain} — "{s.title}"\nURL: {s.url}\n{snippet}')
    return "\n\n".join(lines) if lines else "(нет)"


def _parse_extract_json(
    text: str,
    prefilled: list[Fact],
    fact_slots: list[str] | None = None,
) -> FactPack:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return FactPack(facts=list(prefilled), gaps=["extract_parse_failed"], fact_slots=fact_slots or [])
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return FactPack(facts=list(prefilled), gaps=["extract_json_invalid"], fact_slots=fact_slots or [])

    facts: list[Fact] = list(prefilled)
    seen_claims: set[str] = {f.claim.lower()[:80] for f in prefilled}
    raw_facts = data.get("facts") or []
    if isinstance(raw_facts, list):
        max_facts = 20 if (fact_slots and "course_program" in fact_slots) else 12
        for i, item in enumerate(raw_facts[:max_facts]):
            if not isinstance(item, dict):
                continue
            claim = str(item.get("claim") or "").strip()
            if not claim or claim.lower()[:80] in seen_claims:
                continue
            seen_claims.add(claim.lower()[:80])
            try:
                src_idx = int(item.get("source_index") or 1)
            except (TypeError, ValueError):
                src_idx = 1
            facts.append(
                Fact(
                    id=str(item.get("id") or f"ex{i + 1}"),
                    claim=claim[:500],
                    source_index=max(1, src_idx),
                    quote=str(item.get("quote") or "")[:600],
                    provider="extract",
                    confidence=str(item.get("confidence") or "medium")[:16],
                )
            )

    gaps_raw = data.get("gaps") or []
    gaps = [str(g).strip() for g in gaps_raw if str(g).strip()][:5] if isinstance(gaps_raw, list) else []
    return FactPack(facts=facts, gaps=gaps, fact_slots=fact_slots or [])


async def extract_facts_from_sources(
    llm: "ChatLLM",
    query: str,
    sources: list[SearchSource],
    *,
    prefilled: list[Fact] | None = None,
    fact_slots: list[str] | None = None,
    model: str = "lite",
) -> FactPack:
    prefilled = prefilled or []
    if not sources and not prefilled:
        return FactPack(facts=[], gaps=["no_sources"], fact_slots=fact_slots or [])

    prefilled_text = "\n".join(f"- [{f.source_index}] {f.claim}" for f in prefilled) or "(нет)"
    slots = fact_slots or []
    template = await llm.get_prompt("extract_user", EXTRACT_USER)
    if "course_program" in slots:
        template += await llm.get_prompt("extract_course_addon", EXTRACT_COURSE_ADDON)
    elif "company_financial" in slots:
        template += await llm.get_prompt("extract_financial_addon", EXTRACT_FINANCIAL_ADDON)
    try:
        user_text = template.format(
            query=query[:900],
            prefilled=prefilled_text,
            sources_block=_format_sources_block(sources),
        )
    except KeyError:
        logger.warning("Extract prompt template missing placeholders, using default")
        user_text = EXTRACT_USER.format(
            query=query[:900],
            prefilled=prefilled_text,
            sources_block=_format_sources_block(sources),
        )
    system = await llm.get_prompt("extract_system", EXTRACT_SYSTEM)

    try:
        raw = await llm.complete_text(
            [
                {"role": "system", "text": system},
                {"role": "user", "text": user_text},
            ],
            model=model,  # type: ignore[arg-type]
            max_tokens=2000,
            temperature=0.1,
        )
        pack = _parse_extract_json(raw, prefilled, fact_slots)
        pack.fact_slots = fact_slots or []
        return pack
    except Exception:
        logger.exception("Fact extract failed")
        return FactPack(facts=list(prefilled), gaps=["extract_error"], fact_slots=fact_slots or [])
