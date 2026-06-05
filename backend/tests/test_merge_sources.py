"""Ограничение источников по домену при merge."""

from app.services.facts.merge_sources import (
    DEFAULT_MAX_PER_DOMAIN,
    diversify_sources_by_domain,
    merge_search_sources,
)
from app.services.llm_provider import SearchSource


def _src(url: str, *, title: str = "", domain: str = "") -> SearchSource:
    return SearchSource(
        index=0,
        url=url,
        title=title or url,
        snippet="snippet",
        domain=domain,
    )


def test_diversify_caps_generic_domain_at_two():
    sources = [
        _src("https://habr.com/a", domain="habr.com"),
        _src("https://habr.com/b", domain="habr.com"),
        _src("https://habr.com/c", domain="habr.com"),
        _src("https://vc.ru/x", domain="vc.ru"),
    ]
    out = diversify_sources_by_domain(sources, max_sources=12)
    habr = [s for s in out if "habr.com" in s.url]
    assert len(habr) == DEFAULT_MAX_PER_DOMAIN
    assert len(out) == 3


def test_diversify_allows_more_from_official_domain():
    sources = [
        _src("https://www.cbr.ru/a", domain="cbr.ru"),
        _src("https://www.cbr.ru/b", domain="cbr.ru"),
        _src("https://www.cbr.ru/c", domain="cbr.ru"),
        _src("https://www.cbr.ru/d", domain="cbr.ru"),
        _src("https://habr.com/x", domain="habr.com"),
    ]
    out = diversify_sources_by_domain(sources, max_sources=12)
    cbr = [s for s in out if "cbr.ru" in s.url]
    assert len(cbr) == 4
    assert len(out) == 5


def test_diversify_howto_doc_pages_get_higher_cap():
    sources = [
        _src(
            "https://example.com/docs/guide-1",
            title="Getting started",
            domain="example.com",
        ),
        _src(
            "https://example.com/docs/guide-2",
            title="API reference",
            domain="example.com",
        ),
        _src(
            "https://example.com/docs/guide-3",
            title="Tutorial",
            domain="example.com",
        ),
        _src("https://example.com/blog/post", domain="example.com"),
    ]
    out = diversify_sources_by_domain(sources, howto=True, max_sources=12)
    docs = [s for s in out if "/docs/" in s.url]
    assert len(docs) == 3
    assert len(out) == 3


def test_merge_dedupes_then_diversifies():
    batch_a = [
        _src("https://habr.com/1", domain="habr.com"),
        _src("https://habr.com/2", domain="habr.com"),
        _src("https://habr.com/3", domain="habr.com"),
    ]
    batch_b = [
        _src("https://habr.com/1", domain="habr.com"),
        _src("https://vc.ru/1", domain="vc.ru"),
    ]
    out = merge_search_sources([batch_a, batch_b], max_sources=12)
    assert len([s for s in out if "habr.com" in s.url]) == 2
    assert len(out) == 3
    assert out[0].index == 1
    assert out[-1].index == 3


def test_merge_respects_max_sources_after_diversify():
    sources = [
        _src(f"https://site{i}.com/page", domain=f"site{i}.com")
        for i in range(10)
    ]
    out = merge_search_sources([sources], max_sources=6)
    assert len(out) == 6
