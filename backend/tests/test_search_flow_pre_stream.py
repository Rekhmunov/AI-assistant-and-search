"""Verify/regen must run before first token — no reset_answer for search answers."""

import asyncio
from unittest.mock import MagicMock, patch

from app.services.facts.models import Fact, FactPack
from app.services.search_flow import _generate_refined_search_answer


async def _stream_text(text: str):
    yield text


def test_refined_search_answer_regenerates_on_template_evasion_without_reset():
    calls: list[bool] = []

    async def stream_answer(*_a, strict_facts=False, **_k):
        calls.append(strict_facts)
        if len(calls) == 1:
            yield "В источниках нет информации о данной функции."
        else:
            yield "Курс включает модули по Python и SQL."

    llm = MagicMock()
    llm.stream_answer = stream_answer
    pack = FactPack(facts=[Fact(id="1", claim="курс по Python", source_index=1)])

    answer = asyncio.run(
        _generate_refined_search_answer(
            llm,
            llm_query="курс",
            sources=[],
            llm_history=[],
            model="lite",
            prior_sources_block=None,
            answer_hint=None,
            fact_pack=pack,
            fact_slots=[],
            howto=False,
            grounding_mode="hybrid",
        )
    )

    assert answer == "Курс включает модули по Python и SQL."
    assert len(calls) == 2


def test_refined_search_answer_retries_strict_verify_in_buffer():
    calls: list[bool] = []

    async def stream_answer(*_a, strict_facts=False, **_k):
        calls.append(strict_facts)
        if not strict_facts:
            yield "Курс стоит 999 рублей."
        else:
            yield "Курс стоит 75 рублей."

    llm = MagicMock()
    llm.stream_answer = stream_answer
    pack = FactPack(facts=[Fact(id="1", claim="75 рублей", source_index=1)])

    with patch("app.services.search_flow.verify_answer_against_facts") as verify:
        verify.side_effect = [
            (False, ["999"]),
            (True, []),
        ]
        answer = asyncio.run(
            _generate_refined_search_answer(
                llm,
                llm_query="цена",
                sources=[],
                llm_history=[],
                model="lite",
                prior_sources_block=None,
                answer_hint=None,
                fact_pack=pack,
                fact_slots=["fx_rate"],
                howto=False,
                grounding_mode="strict",
            )
        )

    assert answer == "Курс стоит 75 рублей."
    assert calls == [False, True]
