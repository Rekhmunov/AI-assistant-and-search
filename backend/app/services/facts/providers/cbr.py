from app.services.currency_rates import detect_currency_codes, fetch_cbr_rates
from app.services.facts.models import Fact


class CbrFactProvider:
    slot = "fx_rate"

    async def fetch(self, query: str) -> list[Fact]:
        codes = detect_currency_codes(query)
        result = await fetch_cbr_rates(codes)
        if not result:
            return []
        text, _ = result
        return [
            Fact(
                id="cbr_official",
                claim=text.replace("\n", " ").strip()[:500],
                source_index=1,
                quote=text[:800],
                provider="cbr",
                confidence="high",
            )
        ]
