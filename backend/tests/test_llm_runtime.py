import unittest

from app.services.llm_runtime import build_llm_runtime_status


class TestLlmRuntime(unittest.TestCase):
    def test_mock_when_claude_without_key(self):
        class S:
            anthropic_api_key = ""

            @property
            def anthropic_configured(self):
                return False

        st = build_llm_runtime_status("anthropic_claude", S())  # type: ignore[arg-type]
        self.assertTrue(st["anthropic_mock_active"])
        self.assertIn("ANTHROPIC_API_KEY", st["hint"] or "")

    def test_suffix_when_key_present(self):
        class S:
            anthropic_api_key = "sk-ant-api03-abcdefghijklmnop"

            @property
            def anthropic_configured(self):
                return bool(self.anthropic_api_key.strip())

        st = build_llm_runtime_status("anthropic_claude", S())  # type: ignore[arg-type]
        self.assertEqual(st["anthropic_key_suffix"], "mnop")
        self.assertFalse(st["anthropic_mock_active"])
