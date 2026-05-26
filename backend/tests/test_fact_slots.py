"""Тесты слотов и парсера rewriter (без LLM)."""

import unittest

from app.services.facts.slots import normalize_fact_slots, resolve_fact_slots
from app.services.query_rewriter import _parse_rewrite_json


class TestFactSlots(unittest.TestCase):
    def test_normalize_dedupes_and_filters(self):
        raw = ["fx_rate", "FX_RATE", "bogus", "weather_now"]
        self.assertEqual(normalize_fact_slots(raw), ["fx_rate", "weather_now"])

    def test_resolve_from_rewriter_only(self):
        self.assertEqual(resolve_fact_slots(["fx_rate"]), ["fx_rate"])
        self.assertEqual(resolve_fact_slots(None), [])

    def test_parse_rewrite_json_fact_slots(self):
        text = """
        Вот ответ:
        {"intent": "factual_current", "fact_slots": ["course_program"],
         "search_queries": ["курс похудение программа"], "needs_clarification": false,
         "clarification_question": null, "reason": "course"}
        """
        r = _parse_rewrite_json(text, "fallback")
        assert r is not None
        self.assertEqual(r.fact_slots, ["course_program"])
        self.assertEqual(r.search_queries[0], "курс похудение программа")

    def test_course_not_fx_slot(self):
        text = (
            '{"intent":"factual_current","fact_slots":["course_program"],'
            '"search_queries":["программа похудения"],"needs_clarification":false,'
            '"clarification_question":null,"reason":"x"}'
        )
        r = _parse_rewrite_json(text, "курс на похудение")
        assert r is not None
        self.assertNotIn("fx_rate", r.fact_slots)


if __name__ == "__main__":
    unittest.main()
