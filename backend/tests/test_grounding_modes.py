"""Grounding modes: strict / hybrid / synthesis."""

import unittest

from app.services.facts.grounding import (
    is_hybrid_heuristic_query,
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
