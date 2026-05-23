import base64
import json
from urllib.parse import urlparse

import httpx

from app.core.config import Settings, get_settings
from app.services.llm_provider import SearchSource


MOCK_SOURCES: list[SearchSource] = [
    SearchSource(
        index=1,
        url="https://habr.com/ru/articles/",
        title="Квантовые компьютеры: введение",
        snippet="Квантовые компьютеры используют кубиты и суперпозицию для вычислений.",
        domain="habr.com",
    ),
    SearchSource(
        index=2,
        url="https://ru.wikipedia.org/wiki/Квантовый_компьютер",
        title="Квантовый компьютер — Википедия",
        snippet="Квантовый компьютер — вычислительное устройство, использующее квантовые явления.",
        domain="wikipedia.org",
    ),
    SearchSource(
        index=3,
        url="https://www.rbc.ru/",
        title="Технологии и наука",
        snippet="Обзор развития квантовых технологий в России и мире.",
        domain="rbc.ru",
    ),
]


class YandexSearchService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    async def search(self, query: str, limit: int = 8) -> list[SearchSource]:
        if not self.settings.yandex_configured:
            return [s for s in MOCK_SOURCES[:limit]]

        headers = {
            "Authorization": f"Api-Key {self.settings.yandex_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "query": {
                "searchType": "SEARCH_TYPE_RU",
                "queryText": query,
            },
            "folderId": self.settings.yandex_folder_id,
            "responseFormat": "FORMAT_JSON",
            "maxPassages": 2,
            "region": "225",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.settings.yandex_search_url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()

        raw = data.get("rawData")
        if not raw:
            return MOCK_SOURCES[:limit]

        decoded = json.loads(base64.b64decode(raw).decode("utf-8"))
        sources: list[SearchSource] = []
        docs = decoded.get("response", {}).get("results", []) or decoded.get("results", [])
        for i, doc in enumerate(docs[:limit], start=1):
            url = doc.get("url", "")
            domain = urlparse(url).netloc.replace("www.", "") if url else "unknown"
            sources.append(
                SearchSource(
                    index=i,
                    url=url,
                    title=doc.get("title", domain),
                    snippet=doc.get("passage", doc.get("snippet", ""))[:500],
                    domain=domain,
                )
            )
        return sources or MOCK_SOURCES[:limit]
