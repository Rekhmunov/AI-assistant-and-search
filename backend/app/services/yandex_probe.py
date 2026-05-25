"""Проверка доступности Yandex Search и YandexGPT (для health и админки)."""

import logging

import httpx

from app.core.config import Settings, get_settings
from app.services.yandex_gpt import YandexGPTProvider
from app.services.yandex_search import YandexSearchService

logger = logging.getLogger(__name__)


async def probe_yandex(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    if not s.yandex_configured:
        return {
            "configured": False,
            "search_ok": False,
            "gpt_lite_ok": False,
            "gpt_pro_ok": False,
            "message": "Задайте YANDEX_FOLDER_ID и YANDEX_API_KEY в .env",
        }

    search_ok = False
    gpt_lite_ok = False
    gpt_pro_ok = False
    errors: list[str] = []

    try:
        sources = await YandexSearchService(s).search("тест", limit=1)
        search_ok = len(sources) > 0 and sources[0].domain != "habr.com"
    except httpx.HTTPStatusError as e:
        errors.append(f"search HTTP {e.response.status_code}")
        logger.warning("Yandex search probe failed: %s", e.response.text[:300])
    except Exception as e:
        errors.append(f"search: {e!s}")

    llm = YandexGPTProvider(s)
    try:
        text = await llm.complete_text(
            [{"role": "user", "text": "Ответь одним словом: ок"}],
            model="lite",
            max_tokens=10,
            temperature=0.0,
        )
        gpt_lite_ok = bool(text.strip())
    except httpx.HTTPStatusError as e:
        errors.append(f"gpt_lite HTTP {e.response.status_code}")
        logger.warning("Yandex GPT lite probe failed: %s", e.response.text[:300])
    except Exception as e:
        errors.append(f"gpt_lite: {e!s}")

    try:
        text = await llm.complete_text(
            [{"role": "user", "text": "Ответь одним словом: ок"}],
            model="pro",
            max_tokens=10,
            temperature=0.0,
        )
        gpt_pro_ok = bool(text.strip())
    except httpx.HTTPStatusError as e:
        errors.append(f"gpt_pro HTTP {e.response.status_code}")
        logger.warning("Yandex GPT pro probe failed: %s", e.response.text[:300])
    except Exception as e:
        errors.append(f"gpt_pro: {e!s}")

    ok = search_ok and gpt_lite_ok
    return {
        "configured": True,
        "search_ok": search_ok,
        "gpt_lite_ok": gpt_lite_ok,
        "gpt_pro_ok": gpt_pro_ok,
        "models": {
            "lite": s.yandex_gpt_lite_model,
            "pro": s.yandex_gpt_pro_model,
        },
        "search_url": s.yandex_search_url,
        "ok": ok,
        "errors": errors or None,
        "message": "Все сервисы доступны" if ok and gpt_pro_ok else ("Частично" if ok else "Проверьте ключи и роли в Yandex Cloud"),
    }
