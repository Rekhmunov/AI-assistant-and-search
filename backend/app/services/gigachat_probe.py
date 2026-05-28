"""Проверка GigaChat API (OAuth + lite)."""

from __future__ import annotations

import logging

from app.core.config import Settings, get_settings
from app.services.gigachat import GigaChatProvider, _is_gigachat_pro_payment_error

logger = logging.getLogger(__name__)

_SSL_HINT = (
    " SSL: установите корень НУЦ (Russian Trusted Root CA) — "
    "GIGACHAT_CA_BUNDLE_FILE=/path/in/container/russian_trusted_root_ca.pem "
    "или временно GIGACHAT_VERIFY_SSL_CERTS=false. См. docs/GIGACHAT_SETUP.md"
)


def _format_probe_error(label: str, exc: Exception) -> str:
    msg = str(exc)
    if "CERTIFICATE_VERIFY_FAILED" in msg or "certificate verify failed" in msg.lower():
        return f"{label}: {msg}{_SSL_HINT}"
    return f"{label}: {msg}"


async def probe_gigachat(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    creds = (s.gigachat_credentials or "").strip()
    suffix = creds[-4:] if len(creds) >= 8 else None

    if not s.gigachat_configured:
        return {
            "configured": False,
            "ok": False,
            "credentials_suffix": suffix,
            "message": (
                "GIGACHAT_CREDENTIALS пуст в процессе backend "
                "(проверьте .env и force-recreate; scope GIGACHAT_API_PERS)"
            ),
        }

    llm = GigaChatProvider(s)
    lite_ok = False
    pro_ok = False
    errors: list[str] = []

    try:
        text = await llm.complete_text(
            [{"role": "user", "text": "Ответь одним словом: ок"}],
            model="lite",
            max_tokens=16,
            temperature=0.0,
        )
        lite_ok = bool(text.strip())
    except Exception as e:
        logger.exception("GigaChat probe lite failed")
        errors.append(_format_probe_error("lite", e))

    try:
        text = await llm.complete_text(
            [{"role": "user", "text": "Ответь одним словом: да"}],
            model="pro",
            max_tokens=16,
            temperature=0.0,
        )
        pro_ok = bool(text.strip())
    except Exception as e:
        if _is_gigachat_pro_payment_error(e):
            logger.warning("GigaChat probe pro: 402 Payment Required (lite fallback enabled)")
            errors.append(
                "pro: 402 Payment Required — лимит Pro исчерпан, ответы пойдут через GigaChat-2 (lite)"
            )
        else:
            logger.exception("GigaChat probe pro failed")
            errors.append(_format_probe_error("pro", e))

    ok = lite_ok
    pro_fallback = lite_ok and not pro_ok
    if ok:
        message = f"GigaChat lite и pro ответили ({s.gigachat_model_lite} / {s.gigachat_model_pro})"
    elif lite_ok and not pro_ok:
        message = (
            f"Lite OK ({s.gigachat_model_lite}); pro недоступен — "
            f"{errors[-1] if errors else 'нет ответа'}. "
            "Поиск будет использовать lite как fallback для pro."
        )
    elif pro_ok:
        message = f"Pro OK; lite: {errors[0] if errors else 'нет ответа'}"
    else:
        message = "; ".join(errors) if errors else "Нет ответа от GigaChat"

    return {
        "configured": True,
        "ok": ok,
        "lite_ok": lite_ok,
        "pro_ok": pro_ok,
        "pro_fallback_to_lite": pro_fallback,
        "credentials_suffix": suffix,
        "scope": s.gigachat_scope,
        "models": {"lite": s.gigachat_model_lite, "pro": s.gigachat_model_pro},
        "message": message,
    }
