"""Search Planner v2: парсинг planner JSON без LLM."""

import unittest

from app.services.query_rewriter import (
    _parse_rewrite_json,
    infer_needs_second_search,
    infer_prefer_official_docs,
    normalize_topic_type,
)


class SearchPlannerTests(unittest.TestCase):
    def test_parse_place_query(self):
        text = (
            '{"topic_type":"place","intent":"factual_current","fact_slots":[],'
            '"grounding":"hybrid","search_queries":["Иваново город достопримечательности"],'
            '"needs_second_search":false,"prefer_official_docs":false,'
            '"needs_clarification":false,"clarification_question":null,"reason":"place"}'
        )
        r = _parse_rewrite_json(text, "расскажи про Иваново")
        assert r is not None
        self.assertEqual(r.topic_type, "place")
        self.assertFalse(r.prefer_official_docs)
        self.assertIn("Иваново", r.search_queries[0])

    def test_parse_product_tech(self):
        text = (
            '{"topic_type":"product_tech","intent":"factual_current","fact_slots":[],'
            '"grounding":"hybrid","search_queries":["Telegram Bot API scheduled messages"],'
            '"needs_second_search":false,"prefer_official_docs":true,'
            '"needs_clarification":false,"clarification_question":null,"reason":"bot"}'
        )
        r = _parse_rewrite_json(text, "бот напоминания")
        assert r is not None
        self.assertEqual(r.topic_type, "product_tech")
        self.assertTrue(r.prefer_official_docs)

    def test_infer_prefer_official_from_topic(self):
        self.assertTrue(
            infer_prefer_official_docs(
                topic_type="product_tech",
                intent="factual_current",
                fact_slots=[],
                explicit=None,
            )
        )
        self.assertFalse(
            infer_prefer_official_docs(
                topic_type="place",
                intent="factual_current",
                fact_slots=[],
                explicit=None,
            )
        )

    def test_infer_second_search_for_compare(self):
        self.assertTrue(
            infer_needs_second_search(
                intent="compare_analyze",
                topic_type="general",
                explicit=None,
                query_count=1,
            )
        )

    def test_normalize_topic_type_fallback(self):
        self.assertEqual(normalize_topic_type("unknown"), "general")
        self.assertEqual(normalize_topic_type("place"), "place")


if __name__ == "__main__":
    unittest.main()
