"""Тесты unified runtime helpers."""

from __future__ import annotations

from app.services.agent.agent_runtime import should_run_max_loop_background


def test_background_detection_for_report():
    assert should_run_max_loop_background("пришли отчет excel за месяц по затратам")
    assert not should_run_max_loop_background("1500 + интернет")


def test_background_detection_for_long_text():
    long_text = "затраты " * 200
    assert should_run_max_loop_background(long_text)
