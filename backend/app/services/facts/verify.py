"""Проверка: цифры в ответе должны встречаться в FactPack."""

import re

from app.services.facts.models import FactPack

_ANSWER_NUMBER_RE = re.compile(
    r"(?:"
    r"[+-]?\d{1,3}[.,]\d{1,4}\s*(?:°|₽|руб\.?|р\.?\s*уб\.?|%|USD|EUR)"
    r"|[+-]?\d{1,2}\s*°"
    r"|\d{1,3}[.,]\d{2,6}\s*(?:₽|руб)"
    r")",
    re.I,
)

_CORPUS_NUMBER_RE = re.compile(r"\d{1,3}[.,]?\d{0,6}")


def _normalize_num(token: str) -> str:
    t = token.lower().replace(" ", "")
    for ch in ("°", "₽", "%"):
        t = t.replace(ch, "")
    t = re.sub(r"руб\.?|р\.?уб\.?", "", t)
    return t.replace(",", ".")


def _number_in_corpus(num: str, corpus: str) -> bool:
    n = _normalize_num(num)
    if not n or not re.search(r"\d", n):
        return True
    core = re.search(r"\d{1,3}(?:\.\d+)?", n)
    if not core:
        return True
    val = core.group()
    return val in _normalize_num(corpus)


def verify_answer_against_facts(answer: str, pack: FactPack) -> tuple[bool, list[str]]:
    """
    Возвращает (ok, список чисел в ответе без подтверждения в facts).
    Пустой pack — проверку не блокируем.
    """
    if not answer.strip() or not pack.facts:
        return True, []

    corpus = " ".join(f"{f.claim} {f.quote}" for f in pack.facts)
    found = _ANSWER_NUMBER_RE.findall(answer)
    if not found:
        return True, []

    unsupported: list[str] = []
    for num in found:
        if not _number_in_corpus(num, corpus):
            unsupported.append(num.strip())
    return (len(unsupported) == 0, unsupported)
