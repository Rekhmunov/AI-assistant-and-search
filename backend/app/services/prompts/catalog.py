"""Каталог промптов для админки и валидации ключей настроек."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.prompts.defaults import PROMPT_DEFAULTS


@dataclass(frozen=True)
class PromptDefinition:
    id: str
    label: str
    group: str
    provider: str
    description: str = ""
    rows: int = 8

    @property
    def setting_key(self) -> str:
        return f"prompt_{self.id}"

    @property
    def default(self) -> str:
        return PROMPT_DEFAULTS[self.id]


PROMPT_CATALOG: tuple[PromptDefinition, ...] = (
    PromptDefinition(
        id="yandex_gpt_answer_search",
        label="Ответ с поиском (system)",
        group="Ответ пользователю",
        provider="yandex_gpt",
        description="Основной system-промпт при ответе по источникам [1], [2].",
        rows=14,
    ),
    PromptDefinition(
        id="yandex_gpt_answer_meta",
        label="Ответ «кто ты / что умеешь» (system)",
        group="Ответ пользователю",
        provider="yandex_gpt",
        rows=6,
    ),
    PromptDefinition(
        id="yandex_gpt_answer_direct",
        label="Ответ без поиска (system)",
        group="Ответ пользователю",
        provider="yandex_gpt",
        rows=5,
    ),
    PromptDefinition(
        id="yandex_gpt_answer_document",
        label="Ответ с документом (system)",
        group="Ответ пользователю",
        provider="yandex_gpt",
        rows=8,
    ),
    PromptDefinition(
        id="yandex_gpt_rewriter_system",
        label="Rewriter перед поиском (system)",
        group="Пайплайн поиска",
        provider="yandex_gpt",
        description="Формирует search_queries и fact_slots до вызова Yandex Search.",
        rows=2,
    ),
    PromptDefinition(
        id="yandex_gpt_rewriter_user",
        label="Rewriter перед поиском (user-шаблон)",
        group="Пайплайн поиска",
        provider="yandex_gpt",
        description="Плейсхолдеры: {query}, {history_text}, {continuation_label}.",
        rows=16,
    ),
    PromptDefinition(
        id="yandex_gpt_extract_system",
        label="Извлечение фактов (system)",
        group="Пайплайн поиска",
        provider="yandex_gpt",
        rows=3,
    ),
    PromptDefinition(
        id="yandex_gpt_extract_user",
        label="Извлечение фактов (user-шаблон)",
        group="Пайплайн поиска",
        provider="yandex_gpt",
        description="Плейсхолдеры: {query}, {prefilled}, {sources_block}.",
        rows=12,
    ),
    PromptDefinition(
        id="yandex_gpt_extract_course_addon",
        label="Извлечение: доп. блок «курс/программа»",
        group="Пайплайн поиска",
        provider="yandex_gpt",
        rows=8,
    ),
    PromptDefinition(
        id="yandex_gpt_extract_financial_addon",
        label="Извлечение: доп. блок «финансы»",
        group="Пайплайн поиска",
        provider="yandex_gpt",
        rows=6,
    ),
    PromptDefinition(
        id="yandex_gpt_follow_ups_system",
        label="Подсказки «продолжить тему» (system)",
        group="Прочее",
        provider="yandex_gpt",
        rows=5,
    ),
)

_by_provider: dict[str, list[PromptDefinition]] = {}
for _p in PROMPT_CATALOG:
    _by_provider.setdefault(_p.provider, []).append(_p)
PROMPTS_BY_PROVIDER: dict[str, tuple[PromptDefinition, ...]] = {
    k: tuple(v) for k, v in _by_provider.items()
}

PROMPT_SETTING_KEYS: frozenset[str] = frozenset(p.setting_key for p in PROMPT_CATALOG)
