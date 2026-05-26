"""Проверка DeepSeek API (тестовый запрос lite + pro)."""

from __future__ import annotations

import logging

import httpx

from app.core.config import Settings, get_settings
from app.services.deepseek import DeepSeekProvider

logger = logging.getLogger(__name__)


async def probe_deepseek(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    key = s.deepseek_api_key.strip()
    suffix = key[-4:] if len(key) >= 8 else None

    if not s.deepseek_configured:
        return {
            "configured": False,
            "ok": False,
            "key_suffix": suffix,
            "message": "DEEPSEEK_API_KEY пуст в процессе backend (проверьте .env и force-recreate)",
        }

    llm = DeepSeekProvider(s)
    errors: list[str] = []
    lite_ok = False
    pro_ok = False

    try:
        text = await llm.complete_text(
            [{"role": "user", "text": "Ответь одним словом: ок"}],
            model="lite",
            max_tokens=16,
            temperature=0.0,
        )
        lite_ok = bool(text.strip())
    except httpx.HTTPStatusError as e:
        errors.append(f"lite HTTP {e.response.status_code}")
        logger.warning("DeepSeek lite probe: %s", e.response.text[:300])
    except Exception as e:
        errors.append(f"lite: {e!s}")

    try:
        text = await llm.complete_text(
            [{"role": "user", "text": "Ответь одним словом: ок"}],
            model="pro",
            max_tokens=64,
            temperature=0.0,
        )
        pro_ok = bool(text.strip())
        if not pro_ok:
            errors.append("pro: пустой ответ от API")
    except httpx.HTTPStatusError as e:
        errors.append(f"pro HTTP {e.response.status_code}")
        logger.warning("DeepSeek pro probe: %s", e.response.text[:300])
    except Exception as e:
        errors.append(f"pro: {e!s}")

    ok = lite_ok and pro_ok
    if ok and suffix:
        msg = f"Запрос ушёл в DeepSeek с ключом из .env (суффикс …{suffix})."
    elif lite_ok:
        msg = "Lite OK, Pro с ошибкой — см. errors"
    else:
        msg = "Ошибка — см. errors"
    return {
        "configured": True,
        "ok": ok,
        "lite_ok": lite_ok,
        "pro_ok": pro_ok,
        "key_suffix": suffix,
        "models": {"lite": llm._model_name("lite"), "pro": llm._model_name("pro")},
        "errors": errors or None,
        "message": msg,
    }
