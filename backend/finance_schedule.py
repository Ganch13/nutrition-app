"""Расчёт дат повторяющихся операций и границ бюджетных циклов.

Здесь нет обращений к базе данных: только арифметика дат. Благодаря этому правила легко проверять
тестами на готовых примерах и использовать в любом месте (сервисы, расчёт циклов, оценка нагрузки).

Как задаётся повторение (поле frequency):
  weekly   — каждую неделю в тот же день недели, что и start_on (например, каждая пятница);
  biweekly — раз в две недели, считая от start_on;
  semimonthly — два раза в месяц, в дни day_of_month и second_day_of_month (например 10-го и 25-го);
  monthly  — раз в месяц в день day_of_month (если в месяце меньше дней, берётся последний день:
             правило «31 числа» в феврале сработает 28-го или 29-го);
  yearly   — раз в год в тот же день и месяц, что у start_on (29 февраля в обычный год → 28 февраля).
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

FREQUENCIES = ("weekly", "biweekly", "semimonthly", "monthly", "yearly")

# Частоты, которые могут задавать границы бюджетного цикла (годовой цикл не имеет смысла)
CYCLE_FREQUENCIES = ("weekly", "biweekly", "semimonthly", "monthly")

# Сколько месяцев в «месяце» и недель в году для пересчёта сумм в месячный эквивалент
WEEKS_PER_MONTH = Decimal(52) / Decimal(12)


@dataclass(frozen=True)
class Schedule:
    """Расписание одного правила.

    Примеры: Schedule("monthly", start_on=date(2026, 10, 10), day_of_month=10, end_on=None)
             Schedule("semimonthly", date(2026, 10, 10), day_of_month=10, second_day_of_month=25)
    """

    frequency: str
    start_on: date
    day_of_month: int | None = None
    end_on: date | None = None
    second_day_of_month: int | None = None


def clamp_day(year: int, month: int, day: int) -> date:
    """Дата с днём, не выходящим за пределы месяца. Пример: clamp_day(2026, 2, 31) → 2026-02-28."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def month_start(day: date) -> date:
    """Первое число месяца даты. Пример: 2026-10-28 → 2026-10-01."""
    return day.replace(day=1)


def month_end(day: date) -> date:
    """Последний день месяца даты. Пример: 2026-10-28 → 2026-10-31."""
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def _month_range(first: date, last: date):
    """Перебирает пары (год, месяц) от месяца first до месяца last включительно."""
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        yield year, month
        month += 1
        if month == 13:
            year, month = year + 1, 1


def pattern_dates(schedule: Schedule, first: date, last: date) -> list[date]:
    """Даты по шаблону правила в промежутке [first, last] (границы включаются).

    Шаблон продолжается бесконечно в обе стороны: start_on и end_on здесь НЕ учитываются.
    Это нужно для границ бюджетных циклов, которые должны быть одинаковыми и «до», и «после» даты
    создания правила. Примеры (правило «10-го числа каждого месяца»):
        pattern_dates(Schedule("monthly", date(2026, 1, 10), 10), date(2026, 10, 1), date(2026, 12, 31))
        → [2026-10-10, 2026-11-10, 2026-12-10]
    """
    if first > last:
        return []

    if schedule.frequency in ("weekly", "biweekly"):
        step = 7 if schedule.frequency == "weekly" else 14
        # k0 — номер первого повторения не раньше first (округление вверх целочисленным делением)
        k0 = -((schedule.start_on - first).days // step)
        result = []
        current = schedule.start_on + timedelta(days=k0 * step)
        while current <= last:
            result.append(current)
            current += timedelta(days=step)
        return result

    if schedule.frequency == "monthly":
        day_of_month = schedule.day_of_month or schedule.start_on.day
        found = (clamp_day(year, month, day_of_month) for year, month in _month_range(first, last))
        return [d for d in found if first <= d <= last]

    if schedule.frequency == "semimonthly":
        # Пример: дни 10 и 25 → 10-е и 25-е каждого месяца. Дни 30 и 31 в феврале совпадут
        # (оба станут 28-м), поэтому одинаковые даты убираются
        days = {schedule.day_of_month or schedule.start_on.day}
        if schedule.second_day_of_month is not None:
            days.add(schedule.second_day_of_month)
        found = {
            clamp_day(year, month, day)
            for year, month in _month_range(first, last)
            for day in days
        }
        return sorted(d for d in found if first <= d <= last)

    if schedule.frequency == "yearly":
        anchor = schedule.start_on
        found = (
            clamp_day(year, anchor.month, anchor.day) for year in range(first.year, last.year + 1)
        )
        return [d for d in found if first <= d <= last]

    raise ValueError(f"Неизвестная частота: {schedule.frequency}")


def occurrences(schedule: Schedule, first: date, last: date) -> list[date]:
    """Даты настоящих выплат по правилу в промежутке [first, last].

    В отличие от pattern_dates учитывает срок действия правила: ничего до start_on и после end_on.
    Пример: правило «аванс 10-го» с start_on 2026-10-10 и промежуток 2026-09-01…2026-11-30
    → [2026-10-10, 2026-11-10] (сентябрьской даты нет, правило ещё не действовало).
    """
    low = max(first, schedule.start_on)
    high = min(last, schedule.end_on) if schedule.end_on else last
    if low > high:
        return []
    return pattern_dates(schedule, low, high)


def first_occurrence_on_or_after(schedule: Schedule, day: date, horizon_days: int = 800) -> date | None:
    """Ближайшая выплата не раньше day или None, если правило закончилось. Пример: 2026-10-28 → 2026-11-10."""
    found = occurrences(schedule, day, day + timedelta(days=horizon_days))
    return found[0] if found else None


def monthly_equivalent(amount: Decimal, frequency: str) -> Decimal | None:
    """Сколько правило приносит (или стоит) за месяц, если это можно сказать честно.

    Примеры: 35 000 ₽ раз в месяц → 35 000; 25 000 ₽ два раза в месяц → 50 000;
    10 000 ₽ каждую неделю → 43 333,33 (52/12 недель); 120 000 ₽ раз в год → 10 000.
    Для «раз в две недели» → None: в месяце бывает то две, то три выплаты, и средняя сумма
    не совпадает ни с одним реальным месяцем, поэтому её не показываем.
    """
    if frequency == "monthly":
        value = amount
    elif frequency == "semimonthly":
        value = amount * 2
    elif frequency == "weekly":
        value = amount * WEEKS_PER_MONTH
    elif frequency == "biweekly":
        return None
    elif frequency == "yearly":
        value = amount / 12
    else:
        raise ValueError(f"Неизвестная частота: {frequency}")
    return value.quantize(Decimal("0.01"))


def typical_month_amount(amount: Decimal, frequency: str) -> Decimal:
    """Сумма за обычный месяц для оценки нагрузки.

    Совпадает с monthly_equivalent, кроме «раз в две недели»: там берутся две выплаты — столько
    приходится на большинство месяцев, без пересчёта в среднее (10 000 ₽ → 20 000 ₽).
    """
    value = monthly_equivalent(amount, frequency)
    if value is None:
        value = (amount * 2).quantize(Decimal("0.01"))
    return value


def cycle_boundaries(schedules: list[Schedule], first: date, last: date) -> list[date]:
    """Даты, с которых начинаются бюджетные циклы, в промежутке [first, last], по возрастанию.

    schedules — расписания основных доходов. Пример: аванс 10-го и зарплата 25-го
    → за октябрь [2026-10-10, 2026-10-25].
    """
    dates: set[date] = set()
    for schedule in schedules:
        if schedule.frequency in CYCLE_FREQUENCIES:
            dates.update(pattern_dates(schedule, first, last))
    return sorted(dates)


def cycle_containing(day: date, schedules: list[Schedule]) -> tuple[date, date]:
    """Бюджетный цикл, в который попадает день: (первый день, последний день), оба включительно.

    Если границ нет (основных доходов нет), цикл равен календарному месяцу.
    Примеры при авансе 10-го и зарплате 25-го:
        2026-10-12 → (2026-10-10, 2026-10-24)
        2026-10-28 → (2026-10-25, 2026-11-09)
        2026-10-03 → (2026-09-25, 2026-10-09)
    """
    # Самый длинный промежуток между границами не превышает ~31 дня (раз в месяц), поэтому
    # окна в 70 дней в обе стороны всегда хватает, чтобы найти ближайшие границы
    window = cycle_boundaries(schedules, day - timedelta(days=70), day + timedelta(days=70))
    past = [d for d in window if d <= day]
    future = [d for d in window if d > day]

    if not past or not future:
        return month_start(day), month_end(day)

    return max(past), min(future) - timedelta(days=1)


def next_cycle(end_of_cycle: date, schedules: list[Schedule]) -> tuple[date, date]:
    """Следующий цикл после цикла, закончившегося в end_of_cycle."""
    return cycle_containing(end_of_cycle + timedelta(days=1), schedules)


def previous_cycle(start_of_cycle: date, schedules: list[Schedule]) -> tuple[date, date]:
    """Предыдущий цикл перед циклом, начавшимся в start_of_cycle."""
    return cycle_containing(start_of_cycle - timedelta(days=1), schedules)
