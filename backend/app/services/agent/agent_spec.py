"""Agent Spec — цель, поведение и стабильная память агента."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.agent import AgentInstance


@dataclass
class AgentSpec:
    goal: str | None = None
    behavior: str | None = None
    thread_memory: str = ""
    facts: list[str] = field(default_factory=list)
    task_mode: str | None = None
    categories: list[str] = field(default_factory=list)
    output_format: str | None = None
    triggers: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "behavior": self.behavior,
            "thread_memory": self.thread_memory,
            "facts": self.facts,
            "task_mode": self.task_mode,
            "categories": self.categories,
            "output_format": self.output_format,
            "triggers": self.triggers,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> AgentSpec:
        raw = raw or {}
        facts = raw.get("facts")
        categories = raw.get("categories")
        triggers = raw.get("triggers")
        return cls(
            goal=_str(raw.get("goal")),
            behavior=_str(raw.get("behavior")),
            thread_memory=str(raw.get("thread_memory") or ""),
            facts=[str(x).strip() for x in facts if str(x).strip()] if isinstance(facts, list) else [],
            task_mode=_str(raw.get("task_mode")),
            categories=(
                [str(x).strip() for x in categories if str(x).strip()]
                if isinstance(categories, list)
                else []
            ),
            output_format=_str(raw.get("output_format")),
            triggers=[x for x in triggers if isinstance(x, dict)] if isinstance(triggers, list) else [],
        )


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_agent_spec(agent: AgentInstance) -> AgentSpec:
    cfg = dict(agent.config or {}) if isinstance(agent.config, dict) else {}
    stored = cfg.get("agent_spec")
    if isinstance(stored, dict):
        spec = AgentSpec.from_dict(stored)
    else:
        spec = AgentSpec()
    return _hydrate_from_legacy_config(spec, cfg, agent)


def save_agent_spec(agent: AgentInstance, spec: AgentSpec) -> None:
    cfg = dict(agent.config or {})
    cfg["agent_spec"] = spec.to_dict()
    agent.config = cfg


def _hydrate_from_legacy_config(spec: AgentSpec, cfg: dict[str, Any], agent: AgentInstance) -> AgentSpec:
    if not spec.goal and agent.instruction_text:
        spec.goal = str(agent.instruction_text)[:500]
    if not spec.behavior:
        spec.behavior = _str(cfg.get("support_instructions") or cfg.get("reminder_message"))
    if not spec.task_mode:
        spec.task_mode = _str(cfg.get("task_mode"))
    if not spec.categories and isinstance(cfg.get("expense_categories"), list):
        spec.categories = [str(x) for x in cfg["expense_categories"] if str(x).strip()]
    if not spec.output_format:
        spec.output_format = _str(cfg.get("output_format"))
    checklist = cfg.get("checklist")
    if isinstance(checklist, dict):
        if not spec.goal and checklist.get("role"):
            spec.goal = f"Роль: {checklist.get('role')}"
        if checklist.get("schedule_text"):
            spec.facts.append(f"Расписание: {checklist['schedule_text']}")
        if checklist.get("max_chat_id"):
            spec.facts.append(f"Группа MAX: {checklist['max_chat_id']}")
    if agent.max_chat_id and not any("группа" in f.lower() for f in spec.facts):
        spec.facts.append(f"Группа MAX: {agent.max_chat_id}")
    return spec


def sync_spec_from_checklist(agent: AgentInstance, checklist_dict: dict[str, Any], user_text: str = "") -> AgentSpec:
    spec = load_agent_spec(agent)
    role = checklist_dict.get("role")
    if role:
        spec.goal = spec.goal or f"Агент MAX: {role}"
    if user_text and len(user_text) > 40:
        spec.behavior = user_text[:4000]
    if checklist_dict.get("support_instructions"):
        spec.behavior = str(checklist_dict["support_instructions"])[:4000]
    if checklist_dict.get("reminder_message"):
        spec.behavior = spec.behavior or str(checklist_dict["reminder_message"])[:2000]
    if checklist_dict.get("task_mode"):
        spec.task_mode = str(checklist_dict["task_mode"])
    if checklist_dict.get("expense_categories"):
        spec.categories = list(checklist_dict["expense_categories"])
    if checklist_dict.get("output_format"):
        spec.output_format = str(checklist_dict["output_format"])
    if checklist_dict.get("schedule_text"):
        _upsert_fact(spec, f"Расписание: {checklist_dict['schedule_text']}")
    if checklist_dict.get("max_chat_id"):
        _upsert_fact(spec, f"Группа MAX: {checklist_dict['max_chat_id']}")
    save_agent_spec(agent, spec)
    return spec


def _upsert_fact(spec: AgentSpec, fact: str) -> None:
    fact = fact.strip()
    if not fact:
        return
    prefix = fact.split(":")[0].lower()
    spec.facts = [f for f in spec.facts if not f.lower().startswith(prefix)] + [fact]


def append_fact(spec: AgentSpec, fact: str) -> None:
    fact = fact.strip()
    if fact and fact not in spec.facts:
        spec.facts.append(fact)
        spec.facts = spec.facts[-40:]


def spec_context_block(spec: AgentSpec) -> str:
    lines = ["agent_spec:"]
    if spec.goal:
        lines.append(f"goal: {spec.goal}")
    if spec.behavior:
        lines.append(f"behavior: {spec.behavior[:3000]}")
    if spec.task_mode:
        lines.append(f"task_mode: {spec.task_mode}")
    if spec.categories:
        lines.append(f"categories: {', '.join(spec.categories[:30])}")
    if spec.output_format:
        lines.append(f"output_format: {spec.output_format}")
    if spec.facts:
        lines.append("facts:")
        lines.extend(f"- {f}" for f in spec.facts[-20:])
    if spec.thread_memory:
        lines.append(f"thread_memory:\n{spec.thread_memory[:4000]}")
    return "\n".join(lines)
