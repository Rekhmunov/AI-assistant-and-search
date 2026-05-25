"""Структуры для слоя фактов (FactPack)."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Fact:
    id: str
    claim: str
    source_index: int
    quote: str = ""
    provider: str = "extract"
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "claim": self.claim,
            "source_index": self.source_index,
            "quote": self.quote[:500] if self.quote else "",
            "provider": self.provider,
            "confidence": self.confidence,
        }


@dataclass
class FactPack:
    facts: list[Fact] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    fact_slots: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_slots": self.fact_slots,
            "facts": [f.to_dict() for f in self.facts],
            "gaps": self.gaps,
        }
