"""Слой 0: правила only-LLM vs search+RAG."""

import unittest

from app.models.user import Plan
from app.services.query_router import QueryRouter, is_edit_prior_without_search
from app.services.search_query import is_chitchat_query, is_meta_assistant_query
from app.services.thread_context import ThreadContext


class TestLayer0Rules(unittest.TestCase):
    def test_chitchat_expanded(self):
        for q in ("как дела", "Как у тебя дела?", "добрый день", "что нового", "hey"):
            self.assertTrue(is_chitchat_query(q), q)

    def test_chitchat_not_factual(self):
        self.assertFalse(is_chitchat_query("курс доллара сегодня"))
        self.assertFalse(is_chitchat_query("программа тренировок на месяц для начинающих"))

    def test_meta_expanded(self):
        self.assertTrue(is_meta_assistant_query("Чем можешь помочь?"))
        self.assertTrue(is_meta_assistant_query("Расскажи о себе"))
        self.assertFalse(is_meta_assistant_query("курс Python для начинающих"))

    def test_edit_prior_without_search(self):
        ctx = ThreadContext(
            history=[("user", "x"), ("assistant", "длинный ответ")],
            last_assistant_sources=None,
            is_continuation=True,
            prior_search_used=True,
        )
        self.assertTrue(is_edit_prior_without_search("Сократи ответ короче", ctx))
        self.assertFalse(
            is_edit_prior_without_search("Сократи и найди курс доллара", ctx),
        )

    def test_router_async(self):
        router = QueryRouter()
        empty = ThreadContext([], None, False, False)

        async def run():
            r1 = await router.route("как дела", empty, False, Plan.FREE)
            self.assertFalse(r1.needs_search)
            self.assertEqual(r1.reason, "rules:chitchat")

            r2 = await router.route("курс доллара", empty, False, Plan.FREE)
            self.assertTrue(r2.needs_search)
            self.assertEqual(r2.reason, "search_rag:v6.1")

        import asyncio

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
