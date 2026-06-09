from app.services.answer_sanitize import strip_trailing_empty_code_fences


def test_strip_trailing_empty_fence():
    raw = "Intro\n\n```markdown\n# T\n\nBody\n```\n\n```\n```"
    assert strip_trailing_empty_code_fences(raw).endswith("```")
    assert "```\n```" not in strip_trailing_empty_code_fences(raw)


def test_strip_trailing_open_fence():
    raw = "Intro\n\n```markdown\n# T\n```\n\n```"
    out = strip_trailing_empty_code_fences(raw)
    assert out == "Intro\n\n```markdown\n# T\n```"
