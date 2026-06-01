"""Проверка доступности Perplexity Sonar API."""

from __future__ import annotations

import httpx

from app.core.config import Settings, get_settings


async def probe_perplexity(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    if not s.perplexity_configured:
        return {"ok": False, "error": "PERPLEXITY_API_KEY не задан в .env"}

    url = f"{s.perplexity_base_url.rstrip('/')}/v1/sonar"
    payload = {
        "model": s.perplexity_model_lite,
        "max_tokens": 32,
        "messages": [{"role": "user", "content": "Ответь одним словом: ок"}],
        "disable_search": True,
    }
    headers = {
        "Authorization": f"Bearer {s.perplexity_api_key.strip()}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                detail = (resp.text or "")[:240]
                return {"ok": False, "error": f"HTTP {resp.status_code}: {detail}"}
            data = resp.json()
            text = ""
            choices = data.get("choices") or []
            if choices:
                text = str((choices[0].get("message") or {}).get("content") or "")[:80]
            return {
                "ok": True,
                "model": data.get("model") or s.perplexity_model_lite,
                "sample": text,
            }
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Сеть: {e}"}
