"""Grounding modes: strict / hybrid / synthesis (Search Planner v2)."""

import unittest

from app.services.facts.grounding import (
    adjust_grounding_for_retrieval,
    normalize_grounding,
    resolve_grounding_mode,
    should_verify_answer_numbers,
)
from app.services.answer_guard import search_answer_addon
from app.services.query_rewriter import _parse_rewrite_json


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

    def test_trust_rewriter_hybrid(self):
        mode = resolve_grounding_mode(
            fact_slots=[],
            intent="factual_current",
            rewriter_grounding="hybrid",
            query="расскажи про Иваново",
        )
        self.assertEqual(mode, "hybrid")
        self.assertIn("hybrid", search_answer_addon(grounding=mode).lower())

    def test_trust_rewriter_over_generic_query(self):
        mode = resolve_grounding_mode(
            fact_slots=[],
            intent="factual_current",
            rewriter_grounding="hybrid",
            query="что такое kubernetes",
        )
        self.assertEqual(mode, "hybrid")

    def test_numeric_slot_overrides_rewriter_hybrid(self):
        mode = resolve_grounding_mode(
            fact_slots=["fx_rate"],
            intent="factual_current",
            rewriter_grounding="hybrid",
            query="курс",
        )
        self.assertEqual(mode, "strict")

    def test_howto_is_synthesis(self):
        mode = resolve_grounding_mode(
            fact_slots=[],
            intent="howto",
            rewriter_grounding="hybrid",
            query="как настроить nginx",
        )
        self.assertEqual(mode, "synthesis")

    def test_default_without_rewriter_is_hybrid(self):
        mode = resolve_grounding_mode(
            fact_slots=[],
            intent="factual_current",
            query="любой вопрос",
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

    def test_rewriter_json_grounding(self):
        text = (
            '{"topic_type":"place","intent":"factual_current","fact_slots":[],"grounding":"hybrid",'
            '"search_queries":["Иваново город история"],"needs_second_search":false,'
            '"prefer_official_docs":false,"needs_clarification":false,'
            '"clarification_question":null,"reason":"place"}'
        )
        r = _parse_rewrite_json(text, "fallback")
        assert r is not None
        self.assertEqual(r.grounding, "hybrid")
        self.assertEqual(r.topic_type, "place")
        self.assertFalse(r.prefer_official_docs)
        self.assertEqual(normalize_grounding("HYBRID"), "hybrid")
        self.assertIsNone(normalize_grounding("unknown"))


if __name__ == "__main__":
    unittest.main()
