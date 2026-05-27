"""Низкорисковые оптимизации latency: page fetch budget, extract lite."""

from app.services.llm_provider import SearchSource
from app.services.page_depth import effective_page_fetch_limit, snippet_is_rich


def test_snippet_is_rich_at_threshold():
    assert snippet_is_rich("x" * 1400)
    assert not snippet_is_rich("x" * 1399)


def test_effective_page_fetch_limit_subtracts_rich_sources():
    rich = SearchSource(
        index=1,
        url="https://a.example/1",
        title="A",
        snippet="x" * 1500,
        domain="a.example",
    )
    thin = SearchSource(
        index=2,
        url="https://b.example/2",
        title="B",
        snippet="short",
        domain="b.example",
    )
    assert effective_page_fetch_limit([rich, thin, thin], base_max=3) == 2
    assert effective_page_fetch_limit([rich, rich, rich], base_max=3) == 0


def test_effective_page_fetch_limit_empty_sources():
    assert effective_page_fetch_limit([], base_max=3) == 3
