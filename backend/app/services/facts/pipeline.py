"""Конвейер: Search → fetch → providers → extract → FactPack."""

import logging
from dataclasses import dataclass
from typing import Any

from app.services.currency_rates import cbr_source_from_facts
from app.services.facts.extract import extract_facts_from_sources
from app.services.facts.merge_sources import merge_search_sources
from app.services.facts.models import Fact, FactPack
from app.services.facts.orchestrator import FactOrchestrator
from app.services.facts.slots import detect_fact_slots
from app.services.llm_provider import SearchSource
from app.services.retrieval_quality import assess_retrieval
from app.services.page_depth import FINANCIAL_NUMBER_RE, enrich_sources_deep, is_financial_query
from app.services.source_ranking import rank_sources
from app.services.yandex_gpt import YandexGPTProvider
from app.services.yandex_search import YandexSearchService

logger = logging.getLogger(__name__)

MAX_SEARCH_QUERIES = 3
MAX_FETCH_PAGES = 8
MAX_CHUNKS_PER_PAGE = 4


@dataclass
class FactPipelineResult:
    sources: list[SearchSource]
    fact_pack: FactPack
    search_attempts: list[dict[str, Any]]
    retrieval_trace: dict[str, Any] | None
    last_search_query: str | None


class FactPipeline:
    def __init__(
        self,
        search: YandexSearchService | None = None,
        llm: YandexGPTProvider | None = None,
    ) -> None:
        self.search = search or YandexSearchService()
        self.llm = llm or YandexGPTProvider()
        self.orchestrator = FactOrchestrator()

    async def run(
        self,
        llm_query: str,
        search_queries: list[str],
        *,
        enhance_fn,
        howto: bool = False,
        weather: bool = False,
        currency: bool = False,
        answer_model: str = "lite",
    ) -> FactPipelineResult:
        fact_slots = detect_fact_slots(llm_query)
        search_attempts: list[dict[str, Any]] = []
        batches: list[list[SearchSource]] = []
        last_q: str | None = None

        for base_q in search_queries[:MAX_SEARCH_QUERIES]:
            search_q = enhance_fn(base_q)
            last_q = search_q
            raw = await self.search.search(search_q)
            ranked = rank_sources(
                raw,
                howto=howto or answer_model == "pro",
                weather=weather,
                currency=currency,
            )
            batches.append(ranked)
            assessment = assess_retrieval(ranked, llm_query)
            search_attempts.append(
                {
                    "query": search_q,
                    "sources_count": len(ranked),
                    "retrieval_ok": assessment.ok,
                    "retrieval_score": assessment.score,
                    "retrieval_reason": assessment.reason,
                }
            )
            if assessment.ok and len(batches) >= 1:
                break

        sources = merge_search_sources(batches, max_sources=12)
        retrieval_trace: dict[str, Any] | None = None
        if sources:
            a = assess_retrieval(sources, llm_query)
            retrieval_trace = {
                "ok": a.ok,
                "score": a.score,
                "reason": a.reason,
            }

        provider_facts = await self.orchestrator.fetch_provider_facts(fact_slots, llm_query)
        if provider_facts and "fx_rate" in fact_slots:
            cbr_text = provider_facts[0].quote or provider_facts[0].claim
            cbr_src = cbr_source_from_facts(cbr_text)
            rest = [s for s in sources if "cbr.ru" not in (s.url or "")]
            merged = [cbr_src] + rest[:9]
            sources = [
                SearchSource(
                    index=i,
                    url=s.url,
                    title=s.title,
                    snippet=s.snippet,
                    domain=s.domain,
                )
                for i, s in enumerate(merged, start=1)
            ]
            for i, f in enumerate(provider_facts):
                provider_facts[i] = Fact(
                    id=f.id,
                    claim=f.claim,
                    source_index=1,
                    quote=f.quote,
                    provider=f.provider,
                    confidence=f.confidence,
                )

        if sources:
            chunks_pp = 5 if is_financial_query(llm_query) else MAX_CHUNKS_PER_PAGE
            sources = await enrich_sources_deep(
                sources,
                llm_query,
                max_pages=MAX_FETCH_PAGES,
                chunks_per_page=chunks_pp,
            )
            reassess = assess_retrieval(sources, llm_query)
            retrieval_trace = {
                "ok": reassess.ok,
                "score": reassess.score,
                "reason": f"after_page_fetch:{reassess.reason}",
            }
            search_attempts.append(
                {
                    "query": "(page_fetch)",
                    "sources_count": len(sources),
                    "retrieval_ok": reassess.ok,
                    "retrieval_score": reassess.score,
                    "retrieval_reason": retrieval_trace["reason"],
                }
            )

        fact_pack = await extract_facts_from_sources(
            self.llm,
            llm_query,
            sources,
            prefilled=provider_facts,
            fact_slots=fact_slots,
        )
        if "company_financial" in fact_slots:
            corpus = " ".join((s.snippet or "") for s in sources[:6])
            only_providers = len(fact_pack.facts) <= len(provider_facts)
            if only_providers and FINANCIAL_NUMBER_RE.search(corpus):
                retry_pack = await extract_facts_from_sources(
                    self.llm,
                    llm_query,
                    sources,
                    prefilled=provider_facts,
                    fact_slots=fact_slots,
                    model="pro",
                )
                if len(retry_pack.facts) > len(fact_pack.facts):
                    fact_pack = retry_pack

        return FactPipelineResult(
            sources=sources,
            fact_pack=fact_pack,
            search_attempts=search_attempts,
            retrieval_trace=retrieval_trace,
            last_search_query=last_q,
        )
