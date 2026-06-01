"""Grounding modes: strict / hybrid / synthesis."""

import unittest

from app.services.facts.grounding import (
    adjust_grounding_for_retrieval,
    is_hybrid_heuristic_query,
    is_solution_or_feasibility_query,
    normalize_grounding,
    prefers_official_docs,
    resolve_grounding_mode,
    should_verify_answer_numbers,
)
from app.services.answer_guard import search_answer_addon
from app.services.query_rewriter import _parse_rewrite_json
from app.services.search_query import enhance_search_query


class GroundingModesTests(unittest.TestCase):
    def test_fx_rate_is_strict(self):
        mode = resolve_grounding_mode(
            fact_slots=["fx_rate"],
            intent="factual_current",
            query="курс доллара сегодня",
        )
        self.assertEqual(mode, "strict")
        self.assertTrue(should_verify_answer_numbers(mode, ["fx_rate"]))

    def test_weather_is_strict(self):
        mode = resolve_grounding_mode(
            fact_slots=["weather_now"],
            intent="factual_current",
            query="погода в Москве",
        )
        self.assertEqual(mode, "strict")

    def test_go_function_is_hybrid(self):
        q = "Напиши функцию сортировки на Go"
        self.assertTrue(is_hybrid_heuristic_query(q))
        mode = resolve_grounding_mode(
            fact_slots=[],
            intent="factual_current",
            query=q,
        )
        self.assertEqual(mode, "hybrid")
        self.assertFalse(should_verify_answer_numbers(mode, []))
        self.assertIn("hybrid", search_answer_addon(grounding=mode).lower())

    def test_feasibility_query_is_hybrid(self):
        q = "Можем ли мы сделать напоминания через агента в мессенджере?"
        self.assertTrue(is_solution_or_feasibility_query(q))
        mode = resolve_grounding_mode(
            fact_slots=[],
            intent="factual_current",
            query=q,
        )
        self.assertEqual(mode, "hybrid")

    def test_general_topic_defaults_hybrid(self):
        mode = resolve_grounding_mode(
            fact_slots=[],
            intent="factual_current",
            query="что такое kubernetes",
        )
        self.assertEqual(mode, "hybrid")

    def test_weak_retrieval_upgrades_strict_to_hybrid(self):
        mode = adjust_grounding_for_retrieval(
            "strict",
            weak_retrieval=True,
            fact_slots=[],
        )
        self.assertEqual(mode, "hybrid")

    def test_weak_retrieval_keeps_numeric_strict(self):
        mode = adjust_grounding_for_retrieval(
            "strict",
            weak_retrieval=True,
            fact_slots=["fx_rate"],
        )
        self.assertEqual(mode, "strict")

    def test_prefers_official_docs_for_hybrid(self):
        self.assertTrue(prefers_official_docs("hybrid", intent="compare_analyze"))
        self.assertTrue(prefers_official_docs("hybrid", intent="howto"))

    def test_should_prefer_official_docs_not_for_city(self):
        from app.services.search_query import should_prefer_official_docs

        self.assertFalse(
            should_prefer_official_docs(
                user_query="расскажи про Иваново",
                search_queries=["Иваново город"],
                intent="factual_current",
            )
        )

    def test_should_prefer_official_docs_for_product(self):
        from app.services.search_query import should_prefer_official_docs

        self.assertTrue(
            should_prefer_official_docs(
                user_query="можно ли сделать напоминания через бота в Telegram",
                search_queries=["Telegram Bot API reminders"],
                intent="factual_current",
            )
        )

    def test_enhance_search_query_official_docs(self):
        q = enhance_search_query(
            "Telegram Bot API reminders",
            prefer_official_docs=True,
            for_howto=True,
        )
        self.assertIn("документац", q.lower())

    def test_enhance_search_query_city_unchanged(self):
        q = enhance_search_query(
            "расскажи про Иваново",
            prefer_official_docs=False,
        )
        self.assertNotIn("api", q.lower())
        self.assertIn("Иваново", q)

    def test_howto_is_synthesis(self):
        mode = resolve_grounding_mode(
            fact_slots=[],
            intent="howto",
            query="как настроить nginx",
        )
        self.assertEqual(mode, "synthesis")

    def test_rewriter_json_grounding(self):
        text = (
            '{"intent":"factual_current","fact_slots":[],"grounding":"hybrid",'
            '"search_queries":["go sort example"],"needs_clarification":false,'
            '"clarification_question":null,"reason":"code"}'
        )
        r = _parse_rewrite_json(text, "fallback")
        assert r is not None
        self.assertEqual(r.grounding, "hybrid")
        self.assertEqual(normalize_grounding("HYBRID"), "hybrid")
        self.assertIsNone(normalize_grounding("unknown"))


if __name__ == "__main__":
    unittest.main()
