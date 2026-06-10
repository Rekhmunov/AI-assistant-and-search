"""SEO meta generation for blog posts (Yandex/Google length guidelines)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.blog_ai import _admin_pro_llm

# Ориентиры: Яндекс title до ~70 симв., Google ~55 кириллицы; description Google 120–160,
# Яндекс может взять фрагмент до ~200 из страницы. OG — чуть длиннее для соцсетей.
META_FIELD_LIMITS: dict[str, dict[str, int | str]] = {
    "meta_title": {
        "max": 55,
        "min": 30,
        "label": "Meta title",
        "hint": "Яндекс/Google: 50–55 символов кириллицы, ключ в начале",
    },
    "meta_description": {
        "max": 155,
        "min": 120,
        "label": "Meta description",
        "hint": "Google: 120–155 символов; краткая выгода и призыв",
    },
    "meta_keywords": {
        "max": 100,
        "min": 20,
        "label": "Keywords",
        "hint": "5–8 ключевых фраз через запятую, до 100 символов",
    },
    "og_title": {
        "max": 60,
        "min": 30,
        "label": "OG title",
        "hint": "Заголовок для соцсетей, до 60 символов",
    },
    "og_description": {
        "max": 200,
        "min": 80,
        "label": "OG description",
        "hint": "Описание для превью в соцсетях, до 200 символов",
    },
}

VALID_META_FIELDS = frozenset(META_FIELD_LIMITS)

_FIELD_PROMPTS: dict[str, str] = {
    "meta_title": (
        "Сформируй один SEO meta title для статьи блога Glosix. "
        "Максимум {max} символов (кириллица). Главная ключевая фраза из названия — в начале. "
        "Без кавычек, без слова «Glosix» если не уместно. Только текст заголовка."
    ),
    "meta_description": (
        "Сформируй meta description для статьи блога. "
        "Длина {min}–{max} символов. Одно-два предложения: суть, выгода для читателя, мягкий призыв. "
        "Опирайся на название статьи. Без кавычек в начале/конце. Только текст описания."
    ),
    "meta_keywords": (
        "Подбери ключевые слова для meta keywords: 5–8 фраз через запятую, "
        "всего не длиннее {max} символов. Релевантно названию статьи. Без нумерации. Только список."
    ),
    "og_title": (
        "Сформируй Open Graph title для статьи (превью в соцсетях). "
        "Максимум {max} символов, цепляющий заголовок на основе названия статьи. "
        "Можно чуть эмоциональнее SEO-title. Только текст."
    ),
    "og_description": (
        "Сформируй Open Graph description для соцсетей. "
        "Длина {min}–{max} символов. Интрига или польза, опираясь на название и анонс. Только текст."
    ),
}


@dataclass(frozen=True)
class MetaFieldSpec:
    field: str
    max_length: int
    min_length: int
    label: str
    hint: str


def get_meta_field_spec(field: str) -> MetaFieldSpec:
    if field not in META_FIELD_LIMITS:
        raise ValueError(f"Неизвестное поле meta: {field}")
    raw = META_FIELD_LIMITS[field]
    return MetaFieldSpec(
        field=field,
        max_length=int(raw["max"]),
        min_length=int(raw["min"]),
        label=str(raw["label"]),
        hint=str(raw["hint"]),
    )


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def clamp_meta_text(text: str, *, max_len: int, min_len: int = 0) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip()).strip("«»\"'")
    if not cleaned:
        return ""
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[: max_len + 1]
    # обрезка по последнему пробелу/знаку препинания
    for sep in (". ", "! ", "? ", "; ", ", ", " "):
        idx = cut.rfind(sep)
        if idx >= max(min_len, int(max_len * 0.6)):
            return cut[:idx].strip()
    return cleaned[:max_len].rstrip(" ,.;:-")


def _fallback_meta(field: str, title: str, excerpt: str, spec: MetaFieldSpec) -> str:
    title = title.strip()
    excerpt = (excerpt or "").strip()
    if field == "meta_title":
        base = title
    elif field == "meta_description":
        base = excerpt or f"Узнайте подробнее: {title}"
    elif field == "meta_keywords":
        words = [w for w in re.split(r"[^\wа-яёА-ЯЁ]+", title) if len(w) > 3][:6]
        base = ", ".join(words) if words else title
    elif field == "og_title":
        base = title
    elif field == "og_description":
        base = excerpt or title
    else:
        base = title
    return clamp_meta_text(base, max_len=spec.max_length, min_len=spec.min_length)


async def generate_blog_meta_field(
    db: AsyncSession,
    redis_client,
    *,
    field: str,
    title: str,
    excerpt: str = "",
    content_html: str = "",
) -> dict:
    spec = get_meta_field_spec(field)
    title = title.strip()
    if not title:
        raise ValueError("Укажите заголовок статьи")

    excerpt = (excerpt or "").strip()
    plain = _strip_html(content_html)
    context = f"Название статьи: {title}\n"
    if excerpt:
        context += f"Краткое описание: {excerpt}\n"
    if plain:
        context += f"Фрагмент текста: {plain[:600]}\n"

    system = (
        "Ты SEO-редактор блога Glosix (ИИ-поиск и ассистент). "
        "Пиши на русском, естественно, без спама ключевыми словами. "
        "Верни только готовый текст мета-тега, без пояснений и markdown."
    )
    user = _FIELD_PROMPTS[field].format(max=spec.max_length, min=spec.min_length) + f"\n\n{context}"

    llm = await _admin_pro_llm(db, redis_client)
    try:
        raw = await llm.complete_text(
            [{"role": "system", "text": system}, {"role": "user", "text": user[:3500]}],
            model="lite",
            max_tokens=256,
            temperature=0.35,
        )
        value = clamp_meta_text(raw, max_len=spec.max_length, min_len=0)
    except Exception:
        value = ""

    if not value or (spec.min_length and len(value) < max(10, spec.min_length // 2)):
        value = _fallback_meta(field, title, excerpt, spec)

    value = clamp_meta_text(value, max_len=spec.max_length, min_len=0)
    return {
        "field": field,
        "value": value,
        "max_length": spec.max_length,
        "min_length": spec.min_length,
        "length": len(value),
        "hint": spec.hint,
    }
