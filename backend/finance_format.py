"""Форматирование сумм и дат для текстов-советов, которые сервер пишет словами."""

from datetime import date
from decimal import Decimal

# Знаки популярных валют; для остальных пишется код (например, "KZT")
CURRENCY_SYMBOLS = {"RUB": "₽", "USD": "$", "EUR": "€"}

# Неразрывный пробел: число и знак валюты не разъедутся по разным строкам
NBSP = " "

# Месяцы в родительном падеже в сокращении: «10 ноя»
_MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def money(value: Decimal, currency: str) -> str:
    """Сумма словами для человека.

    Примеры: money(Decimal("35000"), "RUB") → "35 000 ₽"; money(Decimal("1234.5"), "EUR") → "1 234,50 €".
    Копейки показываются только если они есть.
    """
    if value == value.to_integral_value():
        text = f"{value:,.0f}"
    else:
        text = f"{value:,.2f}"
    text = text.replace(",", NBSP).replace(".", ",")
    return f"{text}{NBSP}{CURRENCY_SYMBOLS.get(currency, currency)}"


def short_date(day: date) -> str:
    """Дата без года. Пример: date(2026, 11, 10) → "10 ноя"."""
    return f"{day.day} {_MONTHS[day.month - 1]}"


def period(start: date, end: date) -> str:
    """Период словами. Пример: «10 окт – 24 окт»."""
    return f"{short_date(start)} – {short_date(end)}"
