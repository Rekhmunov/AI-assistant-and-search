"""Форматирование FactPack для промпта YandexGPT."""

from app.services.facts.models import FactPack
from app.services.facts.slots import uses_synthesis_grounding
from app.services.llm_provider import SearchSource


def format_fact_pack_for_prompt(
    pack: FactPack,
    sources: list[SearchSource],
    *,
    fact_slots: list[str] | None = None,
    intent_howto: bool = False,
) -> str:
    slots = fact_slots or pack.fact_slots or []
    synthesis = uses_synthesis_grounding(slots, intent_howto=intent_howto)

    if synthesis:
        header = (
            "=== Материалы из источников (план и рекомендации — собери в связный ответ) ==="
        )
        empty_hint = (
            "(мало извлечённых пунктов — опирайся на фрагменты источников ниже; "
            "не выдумывай точные ккал/вес/сроки, которых нет в тексте)"
        )
    else:
        header = "=== Проверенные факты (точные цифры и даты — только отсюда) ==="
        empty_hint = "(нет извлечённых фактов — цифры только из источников ниже)"

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

    lines.append("\n=== Источники (обязательные ссылки [n] на блоки ниже) ===")
    for s in sources[:8]:
        snippet = (s.snippet or "")[:2200]
        lines.append(f'[{s.index}] {s.domain} — "{s.title}"\n{snippet}')
    return "\n".join(lines)
