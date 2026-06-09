from app.services.prompts.chart_format import ANSWER_CHART_FORMAT
from app.services.prompts.yandex_answer_core import ANSWER_DIRECT, ANSWER_SEARCH


def test_chart_format_mentions_chart_block():
    assert "```chart" in ANSWER_CHART_FORMAT
    assert "GlosixChart v1" in ANSWER_CHART_FORMAT


def test_yandex_answer_prompts_include_chart_format():
    assert "Графики и диаграммы" in ANSWER_SEARCH
    assert "```chart" in ANSWER_DIRECT
