"""Constant-time secret comparison."""

from __future__ import annotations

import hmac


def secrets_match(provided: str | None, expected: str | None) -> bool:
    if not expected:
        return False
    a = (provided or "").encode("utf-8")
    b = expected.encode("utf-8")
    return hmac.compare_digest(a, b)
