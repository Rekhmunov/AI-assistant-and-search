"""Извлечение фактов из источников через YandexGPT (JSON)."""

import json
import logging
import re

from app.services.facts.models import Fact, FactPack
from app.services.llm_provider import SearchSource
from app.services.page_depth import is_financial_query
from app.services.yandex_gpt import YandexGPTProvider

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM = (
    "Ты извлекаешь факты из источников для ответа на вопрос пользователя. "
    "Отвечай ТОЛЬКО валидным JSON без markdown."
)

_EXTRACT_USER_TEMPLATE = """Вопрос пользователя:
{query}

Уже подтверждённые факты (не дублируй):
{prefilled}

Источники:
{sources_block}

Верни JSON:
{{"facts": [{{"id": "f1", "claim": "краткое утверждение", "source_index": 1, "quote": "фрагмент из источника", "confidence": "high|medium"}}], "gaps": ["чего не хватает"]}}

Правила:
- Только факты, явно следующие из источников [n]; не выдумывай цифры.
- claim — на русском, готовое утверждение (температура, курс, дата, определение).
- source_index — номер источника из блока выше.
- Если для ответа на вопрос нет данных — facts пустой, опиши в gaps.
- Максимум 12 фактов."""

_EXTRACT_FINANCIAL_ADDON = """
Дополнительно для финансовых вопросов (оборот, выручка, прибыль):
- Ищи цифры в фрагментах страницы за 2023–2025; указывай год и валюту в claim.
- Если в [1] есть таблица или «оборот» с числом — обязательно добавь fact с source_index 1.
- Не пиши «данных нет», если в тексте источника есть хотя бы одно подходящее число."""


def _format_sources_block(sources: list[SearchSource], max_per: int = 4500) -> str:
    lines: list[str] = []
    for s in sources[:8]:
        snippet = (s.snippet or "")[:max_per]
        lines.append(f'[{s.index}] {s.domain} — "{s.title}"\nURL: {s.url}\n{snippet}')
    return "\n\n".join(lines) if lines else "(нет)"


def _parse_extract_json(text: str, prefilled: list[Fact]) -> FactPack:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return FactPack(facts=list(prefilled), gaps=["extract_parse_failed"])
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return FactPack(facts=list(prefilled), gaps=["extract_json_invalid"])

    facts: list[Fact] = list(prefilled)
    seen_claims: set[str] = {f.claim.lower()[:80] for f in prefilled}
    raw_facts = data.get("facts") or []
    if isinstance(raw_facts, list):
        for i, item in enumerate(raw_facts[:12]):
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
    return FactPack(facts=facts, gaps=gaps)


async def extract_facts_from_sources(
    llm: YandexGPTProvider,
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
    template = _EXTRACT_USER_TEMPLATE
    if is_financial_query(query):
        template += _EXTRACT_FINANCIAL_ADDON
    user_text = template.format(
        query=query[:900],
        prefilled=prefilled_text,
        sources_block=_format_sources_block(sources),
    )

    try:
        raw = await llm.complete_text(
            [
                {"role": "system", "text": _EXTRACT_SYSTEM},
                {"role": "user", "text": user_text},
            ],
            model=model,  # type: ignore[arg-type]
            max_tokens=2000,
            temperature=0.1,
        )
        pack = _parse_extract_json(raw, prefilled)
        pack.fact_slots = fact_slots or []
        return pack
    except Exception:
        logger.exception("Fact extract failed")
        return FactPack(facts=list(prefilled), gaps=["extract_error"], fact_slots=fact_slots or [])
