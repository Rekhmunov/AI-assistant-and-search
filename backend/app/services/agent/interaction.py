"""Режимы взаимодействия агента в MAX: команда, поддержка, группа/личка."""

from __future__ import annotations

import re
from typing import Any

from app.models.agent import AgentInstance, AgentRole
from app.services.agent.profile import agent_config, normalize_dm_command

_VALID_SCOPES = frozenset({"dm", "group", "both"})
_VALID_MODES = frozenset({"command", "support", "both"})

_MENTION_RE = re.compile(r"(?:@|#)\s*\w+|бот\b|glosix\b", re.I)


def agent_scope(cfg: dict[str, Any]) -> str:
    raw = str(cfg.get("scope") or cfg.get("delivery_mode") or "dm").strip().lower()
    if raw == "group":
        return "group"
    if raw == "both":
        return "both"
    return "dm"


def interaction_mode(cfg: dict[str, Any]) -> str:
    raw = str(cfg.get("interaction_mode") or "command").strip().lower()
    return raw if raw in _VALID_MODES else "command"


def support_instructions(agent: AgentInstance, cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or agent_config(agent)
    return str(
        cfg.get("support_instructions")
        or cfg.get("reminder_message")
        or agent.instruction_text
        or ""
    ).strip()


def message_addresses_agent(text: str, command: str | None) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    if command and low.startswith(f"/{command}"):
        return True
    if command and low.startswith(command + " "):
        return True
    if low.startswith("/") and command and low[1:].split()[0] == command:
        return True
    return bool(_MENTION_RE.search(low))


def should_handle_dm(agent: AgentInstance, *, text: str, command: str | None, has_images: bool) -> bool:
    if agent.role != AgentRole.DM_ASSISTANT.value or agent.status != "active":
        return False
    cfg = agent_config(agent)
    mode = interaction_mode(cfg)
    if has_images:
        return True
    if mode == "support":
        return bool((text or "").strip())
    if mode == "both":
        return bool((text or "").strip())
    return bool(command and message_addresses_agent(text, command))


def should_handle_group(
    agent: AgentInstance,
    *,
    text: str,
    command: str | None,
    has_images: bool,
    chat_id: int,
) -> bool:
    if agent.role != AgentRole.DM_ASSISTANT.value or agent.status != "active":
        return False
    cfg = agent_config(agent)
    scope = agent_scope(cfg)
    if scope not in {"group", "both"}:
        return False
    bound_chat = agent.max_chat_id or cfg.get("max_chat_id") or cfg.get("registered_group_chat_id")
    if bound_chat and int(bound_chat) != int(chat_id):
        return False

    mode = interaction_mode(cfg)
    if has_images:
        return True
    if mode == "support":
        return bool((text or "").strip())
    if mode == "both":
        if command and message_addresses_agent(text, command):
            return True
        return bool((text or "").strip())
    if command:
        return message_addresses_agent(text, command)
    return False


def resolve_command_from_text(text: str, cfg: dict[str, Any]) -> tuple[str | None, str]:
    from app.services.agent.dm_commands import parse_dm_command

    command, args = parse_dm_command(text)
    configured = normalize_dm_command(cfg.get("dm_command"))
    if configured and command == configured:
        return configured, args
    if interaction_mode(cfg) == "command" and configured:
        return None, ""
    return command, args
