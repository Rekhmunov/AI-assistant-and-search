"""Сбор контекста треда для роутера и LLM."""

from dataclasses import dataclass

from app.models.message import Message, MessageRole


@dataclass
class ThreadContext:
    history: list[tuple[str, str]]
    last_assistant_sources: list[dict] | None
    is_continuation: bool
    prior_search_used: bool


def build_thread_context(messages: list[Message]) -> ThreadContext:
    history: list[tuple[str, str]] = []
    last_sources: list[dict] | None = None
    prior_search = False

    for m in messages:
        role_val = m.role.value if isinstance(m.role, MessageRole) else str(m.role)
        history.append((role_val, m.content))
        is_assistant = m.role == MessageRole.ASSISTANT or role_val == MessageRole.ASSISTANT.value
        if is_assistant:
            if m.sources:
                last_sources = m.sources if isinstance(m.sources, list) else None
                prior_search = True

    return ThreadContext(
        history=history,
        last_assistant_sources=last_sources,
        is_continuation=len(history) > 0,
        prior_search_used=prior_search,
    )


def format_sources_for_prompt(sources: list[dict] | None, max_items: int = 8) -> str:
    if not sources:
        return ""
    lines = []
    for s in sources[:max_items]:
        idx = s.get("index", "?")
        title = s.get("title", "")
        url = s.get("url", "")
        snippet = (s.get("snippet") or "")[:700]
        lines.append(f"[{idx}] {title}\nURL: {url}\n{snippet}")
    return "Ранее найденные источники:\n" + "\n".join(lines)


def format_history_compact(history: list[tuple[str, str]], max_turns: int = 4, max_chars: int = 600) -> str:
    if not history:
        return ""
    parts = []
    for role, text in history[-max_turns * 2 :]:
        label = "Пользователь" if role == "user" else "Ассистент"
        parts.append(f"{label}: {text[:max_chars]}")
    return "\n".join(parts)
