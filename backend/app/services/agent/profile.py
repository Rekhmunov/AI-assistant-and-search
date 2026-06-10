"""Профиль агента: роли, capabilities, пайплайны контента."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.agent import AgentInstance, AgentRole

# Роли с расписанием (Celery reminders)
SCHEDULED_ROLES = frozenset(
    {
        AgentRole.PERSONAL_REMINDER.value,
        AgentRole.GROUP_REMINDER.value,
        AgentRole.GROUP_MESSAGE_LOG.value,
        AgentRole.NEWS_DIGEST.value,
        AgentRole.IMAGE_POST.value,
    }
)

# Роли без расписания — реагируют на события webhook
EVENT_DRIVEN_ROLES = frozenset(
    {
        AgentRole.GROUP_MODERATION.value,
        AgentRole.DM_ASSISTANT.value,
    }
)

GROUP_ROLES = frozenset(
    {
        AgentRole.GROUP_REMINDER.value,
        AgentRole.GROUP_MESSAGE_LOG.value,
        AgentRole.GROUP_MODERATION.value,
    }
)

VALID_ROLES = SCHEDULED_ROLES | EVENT_DRIVEN_ROLES

USER_TASK_LABELS: dict[str, str] = {
    AgentRole.PERSONAL_REMINDER.value: "уведомления в ваш личный чат MAX",
    AgentRole.GROUP_REMINDER.value: "сообщения в группу MAX",
    AgentRole.GROUP_MESSAGE_LOG.value: "сводки из группы в ваш личный чат MAX",
    AgentRole.NEWS_DIGEST.value: "публикация новостей из интернета в MAX",
    AgentRole.IMAGE_POST.value: "генерация и отправка изображений",
    AgentRole.GROUP_MODERATION.value: "модерация сообщений в группе",
    AgentRole.DM_ASSISTANT.value: "интерактивный помощник в MAX (личка и/или группа)",
}


@dataclass(frozen=True)
class AgentProfile:
    role: str
    content_pipeline: str  # static | llm_generate | group_summary | web_digest | web_digest_images | image_gen
    delivery_mode: str  # dm | group
    needs_schedule: bool
    needs_group: bool
    needs_dm_command: bool
    listens_group_messages: bool
    listens_dm_commands: bool

    @property
    def capabilities(self) -> frozenset[str]:
        caps: set[str] = set()
        if self.delivery_mode == "dm":
            caps.add("dm_out")
        else:
            caps.add("group_out")
        if self.listens_group_messages:
            caps.add("group_in")
        if self.listens_dm_commands:
            caps.add("dm_in")
        if self.content_pipeline in {"web_digest", "web_digest_images"}:
            caps.add("web_search")
        if self.content_pipeline == "web_digest_images":
            caps.add("image_gen")
        if self.content_pipeline == "image_gen":
            caps.add("image_gen")
        if self.content_pipeline == "llm_generate":
            caps.add("llm_generate")
        if self.role == AgentRole.GROUP_MODERATION.value:
            caps.add("moderate")
        return frozenset(caps)


def _delivery_mode(role: str, cfg: dict[str, Any]) -> str:
    explicit = str(cfg.get("delivery_mode") or "").strip().lower()
    if explicit in {"dm", "group"}:
        return explicit
    if role in {AgentRole.GROUP_REMINDER.value, AgentRole.GROUP_MODERATION.value}:
        return "group"
    return "dm"


def _content_pipeline(role: str, cfg: dict[str, Any]) -> str:
    explicit = str(cfg.get("content_pipeline") or "").strip().lower()
    if explicit in {"static", "llm_generate", "group_summary", "web_digest", "web_digest_images", "image_gen"}:
        return explicit
    if role in {AgentRole.PERSONAL_REMINDER.value, AgentRole.GROUP_REMINDER.value}:
        from app.services.agent.generate_content import wants_llm_generated_content

        msg = str(cfg.get("reminder_message") or cfg.get("generation_prompt") or "")
        if wants_llm_generated_content(msg):
            return "llm_generate"
    if role == AgentRole.GROUP_MESSAGE_LOG.value:
        return "group_summary"
    if role in {AgentRole.NEWS_DIGEST.value, AgentRole.DM_ASSISTANT.value} and cfg.get("search_topic"):
        return "web_digest"
    if role in {AgentRole.IMAGE_POST.value, AgentRole.DM_ASSISTANT.value} and cfg.get("image_prompt"):
        return "image_gen"
    if role == AgentRole.NEWS_DIGEST.value:
        return "web_digest"
    if role == AgentRole.IMAGE_POST.value:
        return "image_gen"
    return "static"


def agent_profile(agent: AgentInstance) -> AgentProfile:
    role = str(agent.role or "")
    cfg = dict(agent.config or {}) if isinstance(agent.config, dict) else {}
    delivery = _delivery_mode(role, cfg)
    pipeline = _content_pipeline(role, cfg)
    if role == AgentRole.NEWS_DIGEST.value and delivery == "group":
        needs_group = True
    else:
        needs_group = role in GROUP_ROLES or (delivery == "group" and role in SCHEDULED_ROLES)
    return AgentProfile(
        role=role,
        content_pipeline=pipeline,
        delivery_mode=delivery,
        needs_schedule=role in SCHEDULED_ROLES,
        needs_group=needs_group,
        needs_dm_command=role == AgentRole.DM_ASSISTANT.value,
        listens_group_messages=role in {
            AgentRole.GROUP_MESSAGE_LOG.value,
            AgentRole.GROUP_MODERATION.value,
        }
        or (
            role == AgentRole.DM_ASSISTANT.value
            and (
                str(cfg.get("scope") or "").lower() in {"group", "both"}
                or _delivery_mode(role, cfg) == "group"
            )
        ),
        listens_dm_commands=role == AgentRole.DM_ASSISTANT.value,
    )


def group_setup_roles() -> list[str]:
    """Роли, для которых при bot_added подтягивается chat_id."""
    return [
        AgentRole.GROUP_REMINDER.value,
        AgentRole.GROUP_MESSAGE_LOG.value,
        AgentRole.GROUP_MODERATION.value,
        AgentRole.DM_ASSISTANT.value,
        AgentRole.NEWS_DIGEST.value,
        AgentRole.IMAGE_POST.value,
    ]


def normalize_dm_command(raw: str | None) -> str | None:
    text = (raw or "").strip().lower()
    if not text:
        return None
    if text.startswith("/"):
        text = text[1:]
    return text.split()[0] if text else None


def agent_config(agent: AgentInstance) -> dict[str, Any]:
    raw = agent.config
    return dict(raw) if isinstance(raw, dict) else {}
