"""Поиск картинок через Yandex Search API v2 (/v2/image/search)."""

from __future__ import annotations

import base64
import json
import logging
import re
import xml.etree.ElementTree as ET

import httpx

from app.core.config import Settings, get_settings
from app.services.entity_image import EntityImage
from app.services.image_url_validation import filter_valid_image_urls
from app.services.yandex_errors import YandexServiceError

logger = logging.getLogger(__name__)


def _xml_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    parts = [element.text or ""]
    for child in element:
        parts.append(_xml_text(child))
        if child.tail:
            parts.append(child.tail)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _parse_image_xml(xml_bytes: bytes, limit: int) -> list[tuple[str, str, str, int | None, int | None]]:
    root = ET.fromstring(xml_bytes)
    candidates: list[tuple[str, str, str, int | None, int | None]] = []
    groups = root.findall(".//group") or root.findall(".//doc")
    if root.findall(".//group"):
        for group in root.findall(".//group"):
            for doc in group.findall("doc"):
                candidates.append(_doc_to_candidate(doc))
                if len(candidates) >= limit:
                    return candidates
    else:
        for doc in root.findall(".//doc"):
            candidates.append(_doc_to_candidate(doc))
            if len(candidates) >= limit:
                break
    return candidates[:limit]


def _doc_to_candidate(doc: ET.Element) -> tuple[str, str, str, int | None, int | None]:
    url = _xml_text(doc.find("url"))
    title = _xml_text(doc.find("title")) or _xml_text(doc.find("headline")) or ""
    page_url = _xml_text(doc.find("page-url")) or url
    width: int | None = None
    height: int | None = None
    for prop in doc.findall(".//property"):
        name = (prop.get("name") or "").lower()
        val = _xml_text(prop)
        if name == "width" and val.isdigit():
            width = int(val)
        elif name == "height" and val.isdigit():
            height = int(val)
    return url, title, page_url, width, height


def _parse_image_json(data: dict, limit: int) -> list[tuple[str, str, str, int | None, int | None]]:
    out: list[tuple[str, str, str, int | None, int | None]] = []
    for img in data.get("images") or []:
        url = str(img.get("url") or "").strip()
        if not url:
            continue
        title = str(img.get("pageTitle") or img.get("title") or "").strip()
        page_url = str(img.get("pageUrl") or url).strip()
        w = img.get("width")
        h = img.get("height")
        width = int(w) if str(w or "").isdigit() else None
        height = int(h) if str(h or "").isdigit() else None
        out.append((url, title, page_url, width, height))
        if len(out) >= limit:
            break
    return out


class YandexImageSearchService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    async def search_candidates(
        self,
        query: str,
        *,
        limit: int = 12,
    ) -> list[tuple[str, str, str, int | None, int | None]]:
        if not self.settings.yandex_configured:
            return []
        if not query.strip():
            return []

        headers = {
            "Authorization": f"Api-Key {self.settings.yandex_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "folderId": self.settings.yandex_folder_id.strip(),
            "query": {
                "searchType": "SEARCH_TYPE_RU",
                "queryText": query[:200],
                "familyMode": "FAMILY_MODE_MODERATE",
                "page": 0,
            },
            "imageSpec": {
                "format": "IMAGE_FORMAT_JPEG",
                "size": "IMAGE_SIZE_MEDIUM",
                "orientation": "IMAGE_ORIENTATION_HORIZONTAL",
                "color": "IMAGE_COLOR_COLOR",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                response = await client.post(
                    self.settings.yandex_image_search_url,
                    headers=headers,
                    json=body,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:500]
            logger.warning("Yandex Image Search HTTP %s: %s", e.response.status_code, detail)
            raise YandexServiceError(
                "image_search",
                f"Поиск картинок недоступен (HTTP {e.response.status_code})",
                e.response.status_code,
            ) from e
        except httpx.HTTPError as e:
            logger.exception("Yandex Image Search request failed")
            raise YandexServiceError("image_search", "Поиск картинок недоступен (сеть)") from e

        raw = data.get("rawData")
        if raw:
            try:
                xml_bytes = base64.b64decode(raw)
                return _parse_image_xml(xml_bytes, limit)
            except (ValueError, ET.ParseError):
                logger.exception("Yandex Image Search XML parse failed")

        if data.get("images"):
            return _parse_image_json(data, limit)

        try:
            decoded = json.loads(base64.b64decode(raw).decode("utf-8"))
            return _parse_image_json(decoded, limit)
        except Exception:
            pass

        logger.warning("Yandex Image Search: empty response for %r", query[:80])
        return []

    async def search_validated(
        self,
        query: str,
        *,
        limit: int = 5,
        candidate_limit: int = 14,
        validate_timeout: float = 4.0,
    ) -> list[EntityImage]:
        try:
            candidates = await self.search_candidates(query, limit=candidate_limit)
        except YandexServiceError:
            return []
        if not candidates:
            return []

        valid = await filter_valid_image_urls(
            candidates,
            limit=limit,
            timeout=validate_timeout,
        )
        return [
            EntityImage(
                url=url,
                title=title or "Изображение",
                page_url=page_url or url,
                width=width,
                height=height,
            )
            for url, title, page_url, width, height in valid
        ]
