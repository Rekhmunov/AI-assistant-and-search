"""Оценка качества выдачи Search для решения о повторном запросе."""

import re
from dataclasses import dataclass

from app.services.llm_provider import SearchSource
from app.services.search_query import is_currency_rate_query, is_weather_query

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]{4,}")
_WEATHER_DATA_RE = re.compile(
    r"(-?\d{1,2})\s*°|(-?\d{1,2})\s*град|температур[аы]?\s*(-?\d{1,2})",
    re.I,
)
_CURRENCY_DATA_RE = re.compile(
    r"\d{1,3}[.,]\d{2,6}\s*(?:₽|руб|р\.?\s*уб)|"
    r"(?:USD|EUR|доллар|евро).{0,40}\d{1,3}[.,]\d{2,6}|"
    r"курс.{0,30}\d{1,3}[.,]\d{2,6}|"
    r"официальный\s+курс\s+банка\s+россии",
    re.I,
)

_META_SNIPPET_HINTS = (
    "посетите сайт",
    "перейдите на",
    "воспользуйтесь",
    "где посмотреть",
    "можно найти на",
    "метеорологических сайтах",
    "список сайтов",
    "задачи по поиску информации",
)


@dataclass
class RetrievalAssessment:
    ok: bool
    score: float
    reason: str


def _query_tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def assess_retrieval(sources: list[SearchSource], user_query: str) -> RetrievalAssessment:
    if not sources:
        return RetrievalAssessment(ok=False, score=0.0, reason="no_sources")

    tokens = _query_tokens(user_query)
    if not tokens:
        tokens = _query_tokens(user_query[:200])

    corpus = " ".join(
        f"{s.title} {s.snippet} {s.domain}" for s in sources[:10]
    ).lower()

    if not corpus.strip():
        return RetrievalAssessment(ok=False, score=0.0, reason="empty_snippets")

    hits = sum(1 for t in tokens if t in corpus)
    hit_ratio = hits / max(len(tokens), 1)

    rich = sum(1 for s in sources[:8] if len((s.snippet or "").strip()) >= 40)
    rich_ratio = rich / max(min(len(sources), 8), 1)

    score = 0.55 * hit_ratio + 0.45 * rich_ratio
    ok = score >= 0.22 or (len(sources) >= 4 and rich >= 2)

    if is_weather_query(user_query) and not _WEATHER_DATA_RE.search(corpus):
        ok = False
        reason = f"weather_no_digits hits={hits}/{len(tokens)} rich={rich} score={score:.2f}"
        return RetrievalAssessment(ok=ok, score=score, reason=reason)

    if is_currency_rate_query(user_query) and not _CURRENCY_DATA_RE.search(corpus):
        ok = False
        reason = f"currency_no_rate hits={hits}/{len(tokens)} rich={rich} score={score:.2f}"
        return RetrievalAssessment(ok=ok, score=score, reason=reason)

    meta_hits = sum(1 for h in _META_SNIPPET_HINTS if h in corpus)
    if meta_hits >= 2 and hit_ratio < 0.35:
        ok = False
        reason = f"meta_snippets meta={meta_hits} hits={hits}/{len(tokens)} score={score:.2f}"
        return RetrievalAssessment(ok=ok, score=score, reason=reason)

    reason = f"hits={hits}/{len(tokens)} rich={rich} score={score:.2f}"
    return RetrievalAssessment(ok=ok, score=score, reason=reason)
