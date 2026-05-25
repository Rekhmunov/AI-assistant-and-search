"""Оценка качества выдачи Search для решения о повторном запросе."""

import re
from dataclasses import dataclass

from app.services.llm_provider import SearchSource

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]{4,}")


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

    reason = f"hits={hits}/{len(tokens)} rich={rich} score={score:.2f}"
    return RetrievalAssessment(ok=ok, score=score, reason=reason)
