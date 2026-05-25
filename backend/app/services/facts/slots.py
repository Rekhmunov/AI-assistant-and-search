"""Определение слотов структурированных фактов по запросу."""

from app.services.currency_rates import is_currency_rate_query
from app.services.search_query import is_weather_query


def detect_fact_slots(query: str) -> list[str]:
    slots: list[str] = []
    if is_currency_rate_query(query):
        slots.append("fx_rate")
    if is_weather_query(query):
        slots.append("weather_now")
    return slots
