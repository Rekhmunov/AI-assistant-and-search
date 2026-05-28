"""Vision capability questions without attachment — meta/direct routing."""

import unittest

from app.services.search_query import is_meta_assistant_query, is_vision_capability_question


class VisionCapabilityTests(unittest.TestCase):
    def test_calories_by_photo(self):
        q = "Ты можешь посчитать калории по фото?"
        self.assertTrue(is_meta_assistant_query(q))
        self.assertTrue(is_vision_capability_question(q))

    def test_with_attachment_marker_skipped(self):
        q = "калории по фото\n--- Документ: meal.jpg ---"
        self.assertFalse(is_vision_capability_question(q))

    def test_unrelated_query(self):
        self.assertFalse(is_vision_capability_question("курс Python для начинающих"))


if __name__ == "__main__":
    unittest.main()
