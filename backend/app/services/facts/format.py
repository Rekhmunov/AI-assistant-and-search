"""Форматирование FactPack для промпта YandexGPT."""

from app.services.facts.models import FactPack
from app.services.llm_provider import SearchSource


def format_fact_pack_for_prompt(pack: FactPack, sources: list[SearchSource]) -> str:
    lines = ["=== Проверенные факты (цифры и даты только отсюда) ==="]
    if pack.facts:
        for f in pack.facts:
            lines.append(f"[{f.source_index}] ({f.provider}) {f.claim}")
            if f.quote and f.provider != "cbr":
                lines.append(f"    Цитата: {f.quote[:280]}")
    else:
        lines.append("(нет извлечённых фактов — опирайся на источники ниже, не выдумывай цифры)")

    if pack.gaps:
        lines.append("Пробелы в данных: " + "; ".join(pack.gaps[:4]))

    lines.append("\n=== Источники (для цитат [n]) ===")
    for s in sources[:8]:
        snippet = (s.snippet or "")[:700]
        lines.append(f'[{s.index}] {s.domain} — "{s.title}"\n{snippet}')
    return "\n".join(lines)
