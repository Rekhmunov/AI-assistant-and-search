"""Объединение результатов нескольких поисковых запросов."""

from app.services.llm_provider import SearchSource


def merge_search_sources(
    batches: list[list[SearchSource]],
    *,
    max_sources: int = 12,
) -> list[SearchSource]:
    seen: set[str] = set()
    merged: list[SearchSource] = []
    for batch in batches:
        for s in batch:
            key = (s.url or "").strip().lower() or f"title:{s.title}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(s)
            if len(merged) >= max_sources:
                break
        if len(merged) >= max_sources:
            break
    return [
        SearchSource(
            index=i,
            url=s.url,
            title=s.title,
            snippet=s.snippet,
            domain=s.domain,
        )
        for i, s in enumerate(merged, start=1)
    ]
