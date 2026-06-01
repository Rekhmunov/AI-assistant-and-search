"""Perplexity Sonar: маппинг источников и фабрика провайдера."""

from app.services.perplexity_sources import map_perplexity_sources
from app.services.providers.factory import create_llm_provider, llm_model_label
from app.services.perplexity import PerplexityProvider, is_perplexity_provider
from app.services.prompts.store import PromptStore


def test_map_search_results_preferred_over_citations():
    sources = map_perplexity_sources(
        search_results=[
            {
                "title": "Иваново — Wikipedia",
                "url": "https://ru.wikipedia.org/wiki/Иваново",
                "snippet": "Город в России",
            }
        ],
        citations=["https://example.com/other"],
    )
    assert len(sources) == 1
    assert sources[0].index == 1
    assert "Иваново" in sources[0].title
    assert sources[0].snippet == "Город в России"


def test_map_citations_fallback():
    sources = map_perplexity_sources(citations=["https://docs.perplexity.ai/start"])
    assert len(sources) == 1
    assert sources[0].url.startswith("https://docs.perplexity.ai")


def test_create_perplexity_provider():
    llm = create_llm_provider("perplexity", None, PromptStore(None, None))  # type: ignore[arg-type]
    assert isinstance(llm, PerplexityProvider)


def test_llm_model_label_perplexity():
    llm = create_llm_provider("perplexity", None, PromptStore(None, None))  # type: ignore[arg-type]
    assert llm_model_label(llm, "lite") == "sonar"
    assert llm_model_label(llm, "pro") == "sonar-pro"


def test_is_perplexity_provider():
    assert is_perplexity_provider("perplexity")
    assert not is_perplexity_provider("yandex_gpt")
