import base64
import json
import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx

from app.core.config import Settings, get_settings
from app.services.llm_provider import SearchSource
from app.services.yandex_errors import YandexServiceError

logger = logging.getLogger(__name__)

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


def _xml_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    parts = [element.text or ""]
    for child in element:
        parts.append(_xml_text(child))
        if child.tail:
            parts.append(child.tail)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _parse_yandex_xml(xml_bytes: bytes, limit: int) -> list[SearchSource]:
    root = ET.fromstring(xml_bytes)
    docs = root.findall(".//doc")
    sources: list[SearchSource] = []
    for i, doc in enumerate(docs[:limit], start=1):
        url = _xml_text(doc.find("url"))
        title = _xml_text(doc.find("title")) or _xml_text(doc.find("headline"))
        passage_el = doc.find("passages/passage")
        snippet = _xml_text(passage_el) or _xml_text(doc.find("headline"))
        domain = urlparse(url).netloc.replace("www.", "") if url else "unknown"
        if not url and not title:
            continue
        sources.append(
            SearchSource(
                index=i,
                url=url,
                title=title or domain,
                snippet=snippet[:900],
                domain=domain,
            )
        )
    return sources


def _parse_search_documents(decoded: dict, limit: int) -> list[SearchSource]:
    docs: list[dict] = []
    response = decoded.get("response") or decoded
    if isinstance(response, dict):
        docs = list(response.get("results") or [])
        if not docs:
            for group in response.get("groups") or []:
                docs.extend(group.get("documents") or group.get("docs") or [])
    if not docs:
        docs = list(decoded.get("results") or [])

    sources: list[SearchSource] = []
    for i, doc in enumerate(docs[:limit], start=1):
        url = doc.get("url", "")
        domain = urlparse(url).netloc.replace("www.", "") if url else "unknown"
        snippet = doc.get("passage") or doc.get("snippet") or doc.get("description") or ""
        sources.append(
            SearchSource(
                index=i,
                url=url,
                title=doc.get("title", domain),
                snippet=str(snippet)[:900],
                domain=domain,
            )
        )
    return sources


class YandexSearchService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    async def search(self, query: str, limit: int = 10) -> list[SearchSource]:
        if not self.settings.yandex_configured:
            return [s for s in MOCK_SOURCES[:limit]]

        headers = {
            "Authorization": f"Api-Key {self.settings.yandex_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "query": {
                "searchType": "SEARCH_TYPE_RU",
                "queryText": query[:400],
            },
            "folderId": self.settings.yandex_folder_id.strip(),
            "responseFormat": "FORMAT_XML",
            "maxPassages": "4",
            "region": "225",
            "l10n": "LOCALIZATION_RU",
            "groupSpec": {
                "groupMode": "GROUP_MODE_FLAT",
                "groupsOnPage": str(min(limit, 20)),
                "docsInGroup": "1",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.settings.yandex_search_url, headers=headers, json=body)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:500]
            logger.error("Yandex Search HTTP %s: %s", e.response.status_code, detail)
            raise YandexServiceError("search", f"Поиск недоступен (HTTP {e.response.status_code})", e.response.status_code) from e
        except httpx.HTTPError as e:
            logger.exception("Yandex Search request failed")
            raise YandexServiceError("search", "Поиск недоступен (сеть)") from e

        raw = data.get("rawData")
        if not raw:
            logger.warning("Yandex Search empty rawData: %s", list(data.keys()))
            raise YandexServiceError("search", "Пустой ответ Search API")

        try:
            xml_bytes = base64.b64decode(raw)
        except ValueError as e:
            logger.exception("Yandex Search rawData base64 decode failed")
            raise YandexServiceError("search", "Некорректный ответ Search API") from e

        try:
            sources = _parse_yandex_xml(xml_bytes, limit)
        except ET.ParseError as e:
            logger.exception("Yandex Search XML parse failed")
            raise YandexServiceError("search", "Некорректный XML в ответе Search API") from e
        if not sources:
            # fallback: legacy JSON-in-base64 (если API вернёт JSON)
            try:
                decoded = json.loads(xml_bytes.decode("utf-8"))
                sources = _parse_search_documents(decoded, limit)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        if not sources:
            logger.warning("Yandex Search: no documents in response (empty SERP)")
        return sources
