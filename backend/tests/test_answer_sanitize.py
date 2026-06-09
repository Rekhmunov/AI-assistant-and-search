from app.services.answer_sanitize import strip_trailing_empty_code_fences


def test_strip_trailing_empty_fence():
    raw = "Intro\n\n```markdown\n# T\n\nBody\n```\n\n```\n```"
    out = strip_trailing_empty_code_fences(raw)
    assert out == "Intro\n\n```markdown\n# T\n\nBody\n```"


def test_keeps_valid_markdown_closing_fence():
    raw = "Intro\n\n```markdown\n# T\n```"
    assert strip_trailing_empty_code_fences(raw) == raw
