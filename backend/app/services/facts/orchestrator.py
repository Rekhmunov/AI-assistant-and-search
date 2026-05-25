"""Плагины структурированных фактов (ЦБ и др.)."""

from app.services.facts.models import Fact
from app.services.facts.providers.cbr import CbrFactProvider


class FactOrchestrator:
    def __init__(self) -> None:
        self._providers = {
            CbrFactProvider.slot: CbrFactProvider(),
        }

    async def fetch_provider_facts(self, slots: list[str], query: str) -> list[Fact]:
        facts: list[Fact] = []
        for slot in slots:
            provider = self._providers.get(slot)
            if provider:
                facts.extend(await provider.fetch(query))
        return facts
