"""Пост-обработка ответа: документы в блоке ```markdown и правки черновика."""

from __future__ import annotations

import re

from app.services.doc_gen_routing import wants_document_generation

_MD_FENCE_RE = re.compile(r"```(?:markdown|md)\b", re.I)
_LEGAL_DOC_RE = re.compile(
    r"(?i)(?:оферт|договор|соглашен|заявлен|политик|регламент|устав|приказ|трудов|аренд|поставк|услуг|подряд)",
)
_TEMPLATE_RE = re.compile(
    r"(?i)(?:болванк|шаблон|образец|типовой|пример\s+договор|пример\s+документ)",
)
# Данные которые уже содержатся в запросе — нет нужды уточнять
_HAS_PARTIES_RE = re.compile(
    r"(?i)(?:ооо|ип|ао|пао|зао|нко|физлицо)\s+[\w\u00ab\u00bb\u201c\u201d]|между\s+\w|\bстороны\b.{0,30}\bдоговор",
)


def has_markdown_document_fence(text: str) -> bool:
    return bool(_MD_FENCE_RE.search(text or ""))


def is_legal_document_request(query: str) -> bool:
    return bool(_LEGAL_DOC_RE.search(query or ""))


def is_template_request(query: str) -> bool:
    """Пользователь просит болванку/шаблон — не нужно уточнять данные."""
    return bool(_TEMPLATE_RE.search(query or ""))


def has_parties_data(query: str) -> bool:
    """Данные о сторонах уже есть в запросе."""
    return bool(_HAS_PARTIES_RE.search(query or ""))


def needs_data_clarification(query: str) -> bool:
    """
    Нужен ли уточняющий вопрос перед генерацией.
    Не нужен если: это болванка/шаблон, или данные уже есть в запросе.
    """
    if not is_legal_document_request(query):
        return False
    if is_template_request(query):
        return False
    if has_parties_data(query):
        return False
    return True


# Поисковые запросы для поиска законодательной базы по типу документа
_DOC_SEARCH_HINTS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"(?i)договор\s+аренд"), [
        "договор аренды нежилого помещения обязательные условия ГК РФ 2026",
        "существенные условия договора аренды статья 432 614 ГК РФ",
    ]),
    (re.compile(r"(?i)трудов\w+\s+договор|договор\s+труд"), [
        "трудовой договор обязательные условия статья 57 ТК РФ 2026",
        "содержание трудового договора ТК РФ обязательные реквизиты",
    ]),
    (re.compile(r"(?i)публичн\w+\s+оферт|договор\s+оферт|оферт"), [
        "публичная оферта требования статья 437 ГК РФ 2026",
        "публичная оферта дистанционная торговля ЗоЗПП требования",
    ]),
    (re.compile(r"(?i)договор\s+поставк"), [
        "договор поставки существенные условия статья 506 ГК РФ 2026",
        "договор поставки товаров обязательные условия",
    ]),
    (re.compile(r"(?i)договор\s+оказани\w+\s+услуг|возмездное\s+оказани"), [
        "договор возмездного оказания услуг статья 779 ГК РФ существенные условия",
    ]),
    (re.compile(r"(?i)договор\s+подряд"), [
        "договор подряда существенные условия статья 702 ГК РФ 2026",
    ]),
    (re.compile(r"(?i)политик\w+\s+конфиден|privacy"), [
        "политика конфиденциальности требования 152-ФЗ персональные данные 2026",
    ]),
    (re.compile(r"(?i)должностн\w+\s+инструкц"), [
        "должностная инструкция требования трудовое законодательство РФ 2026",
    ]),
]


def get_legal_search_queries(query: str) -> list[str]:
    """Возвращает поисковые запросы для поиска правовой базы по типу документа."""
    for pattern, queries in _DOC_SEARCH_HINTS:
        if pattern.search(query or ""):
            return queries
    if is_legal_document_request(query):
        # Общий запрос для неизвестного типа документа
        return [f"{query.strip()[:80]} требования законодательство РФ 2026 обязательные условия"]
    return []


def document_request_prompt_addon(query: str) -> str:
    if not wants_document_generation(query):
        return ""
    legal = is_legal_document_request(query)
    is_template = is_template_request(query)

    lines = [
        "\n\nДОПОЛНЕНИЕ К ЗАДАЧЕ — ГЕНЕРАЦИЯ ДОКУМЕНТА:",
        "1. Весь текст документа помести в ОДИН блок ```markdown … ``` с заголовками # и ## внутри блока.",
        "   Вне блока — только 1–2 предложения введения.",
        "2. НЕ СОКРАЩАЙ: каждый раздел должен содержать полный юридически корректный текст, минимум 3–5 абзацев.",
        "3. Не используй заглушки вида «перечислить условия» или «указать требования» — пиши конкретный текст.",
    ]

    if legal:
        if is_template:
            lines.append(
                "4. Это шаблон: используй плейсхолдеры [НАЗВАНИЕ КОМПАНИИ], [ИНН], [АДРЕС], "
                "[ДАТА], [СУММА] для всех реквизитов."
            )
        else:
            lines.append(
                "4. Если в запросе есть конкретные данные сторон — вставляй их в документ напрямую."
                " Если данных нет — используй плейсхолдеры [НАЗВАНИЕ], [ИНН], [АДРЕС]."
            )
        lines.append(
            "5. Используй актуальные нормы из источников [n] с номерами статей (например: ст. 614 ГК РФ)."
            " Если источники содержат конкретные нормы — обязательно включи ссылки в текст."
        )
        lines.append(
            "6. ОБЯЗАТЕЛЬНЫЕ РАЗДЕЛЫ для договоров: Предмет; Цена и порядок расчётов; "
            "Права и обязанности сторон; Ответственность сторон; Срок действия; "
            "Форс-мажор; Порядок разрешения споров; Реквизиты и подписи сторон."
        )

    return "\n".join(lines)


def edit_document_prompt_addon(query: str) -> str:
    q = (query or "").lower()
    hints = (
        "раздел",
        "документ",
        "оферт",
        "договор",
        "заявлен",
        "реквизит",
        "плейсхолдер",
        "диаграм",
        "график",
        "chart",
        "визуал",
        "вставь",
        "добавь",
    )
    if not any(h in q for h in hints):
        return ""
    return (
        "\n\nДополнение: правка документа из диалога.\n"
        "- Весь текст документа — в ОДНОМ блоке ```markdown … ``` (заголовки # / ##, нумерация).\n"
        "- Если нужна диаграмма — сразу ПОСЛЕ закрывающих ``` markdown добавь один блок ```chart "
        "с JSON GlosixChart (не внутри markdown, не вторым markdown-блоком после chart).\n"
        "- Не разбивай документ на несколько блоков ```markdown … ```."
    )


def ensure_markdown_document_answer(answer: str, query: str) -> tuple[str, bool]:
    """
    Оборачивает длинный ответ в ```markdown, если запрос на документ, а модель не использовала блок.
    Возвращает (текст, changed).
    """
    body = (answer or "").strip()
    if not body or has_markdown_document_fence(body):
        return answer, False
    if not wants_document_generation(query):
        return answer, False
    if len(body) < 280:
        return answer, False

    looks_structured = bool(
        re.search(r"(?m)^#{1,3}\s+\S", body)
        or re.search(r"(?m)^\d+(?:\.\d+)*\.?\s+\S", body)
        or len(body) >= 900
    )
    if not looks_structured:
        return answer, False

    intro = "Ниже полный текст документа."
    wrapped = f"{intro}\n\n```markdown\n{body}\n```"
    return wrapped, True
