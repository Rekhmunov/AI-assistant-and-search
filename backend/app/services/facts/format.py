"""Форматирование FactPack для промпта YandexGPT."""

from app.services.facts.grounding import GroundingMode, effective_grounding_for_prompt
from app.services.facts.models import FactPack
from app.services.llm_provider import SearchSource


def format_fact_pack_for_prompt(
    pack: FactPack,
    sources: list[SearchSource],
    *,
    fact_slots: list[str] | None = None,
    intent_howto: bool = False,
    grounding: GroundingMode = "strict",
) -> str:
    slots = fact_slots or pack.fact_slots or []
    mode = effective_grounding_for_prompt(grounding, slots, intent_howto=intent_howto)

    if mode == "hybrid":
        header = (
            "=== Справка из сети (дополняет твои знания; [n] — только на факты из блоков ниже) ==="
        )
        empty_hint = (
            "(мало фактов в выдаче — ответь из знаний модели; актуальные цифры и даты — только из [n])"
        )
        sources_header = "\n=== Источники (цитируй [n] только для фактов из сети) ==="
    elif mode == "synthesis":
        header = (
            "=== Материалы из источников (план и рекомендации — собери в связный ответ) ==="
        )
        empty_hint = (
            "(мало извлечённых пунктов — опирайся на фрагменты источников ниже; "
            "не выдумывай точные ккал/вес/сроки, которых нет в тексте)"
        )
        sources_header = "\n=== Источники (обязательные ссылки [n] на блоки ниже) ==="
    else:
        header = "=== Проверенные факты (точные цифры и даты — только отсюда) ==="
        empty_hint = "(нет извлечённых фактов — цифры только из источников ниже)"
        sources_header = "\n=== Источники (обязательные ссылки [n] на блоки ниже) ==="

    lines = [header]
    if pack.facts:
        for f in pack.facts:
            lines.append(f"[{f.source_index}] ({f.provider}) {f.claim}")
            if f.quote and f.provider != "cbr":
                lines.append(f"    Цитата: {f.quote[:280]}")
    else:
        lines.append(empty_hint)

    if pack.gaps:
        lines.append("Пробелы в данных: " + "; ".join(pack.gaps[:4]))

    lines.append(sources_header)
    for s in sources[:8]:
        snippet = (s.snippet or "")[:2200]
        lines.append(f'[{s.index}] {s.domain} — "{s.title}"\n{snippet}')
    return "\n".join(lines)
