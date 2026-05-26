"""Проверка Anthropic API (тестовый запрос — появится в console.anthropic.com)."""

from __future__ import annotations

import logging

import httpx

from app.core.config import Settings, get_settings
from app.services.anthropic_claude import AnthropicClaudeProvider

logger = logging.getLogger(__name__)


async def probe_anthropic(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    suffix = (s.anthropic_api_key.strip()[-4:] if len(s.anthropic_api_key.strip()) >= 8 else None)

    if not s.anthropic_configured:
        return {
            "configured": False,
            "ok": False,
            "key_suffix": suffix,
            "message": "ANTHROPIC_API_KEY пуст в процессе backend (проверьте .env и force-recreate)",
        }

    llm = AnthropicClaudeProvider(s)
    model_lite = llm._model_name("lite")
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
        logger.warning("Anthropic lite probe: %s", e.response.text[:300])
    except Exception as e:
        errors.append(f"lite: {e!s}")

    try:
        text = await llm.complete_text(
            [{"role": "user", "text": "Ответь одним словом: ок"}],
            model="pro",
            max_tokens=16,
            temperature=0.0,
        )
        pro_ok = bool(text.strip())
    except httpx.HTTPStatusError as e:
        errors.append(f"pro HTTP {e.response.status_code}")
        logger.warning("Anthropic pro probe: %s", e.response.text[:300])
    except Exception as e:
        errors.append(f"pro: {e!s}")

    ok = lite_ok and pro_ok
    if ok and suffix:
        msg = f"Запрос ушёл в Anthropic с ключом из .env (суффикс …{suffix}). Проверьте Usage в консоли."
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
        "models": {"lite": model_lite, "pro": llm._model_name("pro")},
        "errors": errors or None,
        "message": msg,
    }
