"""Проверки расчёта дат повторяющихся операций и границ бюджетных циклов (без базы данных)."""

from datetime import date
from decimal import Decimal

from finance_schedule import (
    Schedule,
    cycle_boundaries,
    cycle_containing,
    first_occurrence_on_or_after,
    monthly_equivalent,
    next_cycle,
    occurrences,
    pattern_dates,
    previous_cycle,
    typical_month_amount,
)

ADVANCE = Schedule("monthly", date(2026, 1, 10), 10)  # аванс 10-го
SALARY = Schedule("monthly", date(2026, 1, 25), 25)  # зарплата 25-го


def test_monthly_uses_last_day_of_short_months():
    # «31 числа» в феврале срабатывает 28-го
    schedule = Schedule("monthly", date(2026, 1, 31), 31)
    assert pattern_dates(schedule, date(2026, 1, 1), date(2026, 4, 30)) == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]


def test_weekly_and_biweekly_count_from_start_date():
    # start_on — пятница 2 октября 2026
    weekly = Schedule("weekly", date(2026, 10, 2))
    assert pattern_dates(weekly, date(2026, 10, 10), date(2026, 10, 31)) == [
        date(2026, 10, 16),
        date(2026, 10, 23),
        date(2026, 10, 30),
    ]
    biweekly = Schedule("biweekly", date(2026, 10, 2))
    assert pattern_dates(biweekly, date(2026, 9, 1), date(2026, 10, 31)) == [
        date(2026, 9, 4),
        date(2026, 9, 18),
        date(2026, 10, 2),
        date(2026, 10, 16),
        date(2026, 10, 30),
    ]


def test_yearly_handles_leap_day():
    schedule = Schedule("yearly", date(2024, 2, 29))
    assert pattern_dates(schedule, date(2026, 1, 1), date(2028, 12, 31)) == [
        date(2026, 2, 28),
        date(2027, 2, 28),
        date(2028, 2, 29),
    ]


def test_occurrences_respect_start_and_end():
    schedule = Schedule("monthly", date(2026, 10, 10), 10, end_on=date(2026, 12, 31))
    assert occurrences(schedule, date(2026, 9, 1), date(2027, 3, 31)) == [
        date(2026, 10, 10),
        date(2026, 11, 10),
        date(2026, 12, 10),
    ]
    assert occurrences(schedule, date(2027, 1, 1), date(2027, 3, 31)) == []
    assert first_occurrence_on_or_after(schedule, date(2026, 11, 11)) == date(2026, 12, 10)
    assert first_occurrence_on_or_after(schedule, date(2027, 1, 1)) is None


def test_monthly_equivalent():
    assert monthly_equivalent(Decimal("35000"), "monthly") == Decimal("35000.00")
    assert monthly_equivalent(Decimal("10000"), "weekly") == Decimal("43333.33")
    assert monthly_equivalent(Decimal("25000"), "semimonthly") == Decimal("50000.00")
    # Раз в две недели в среднее не пересчитывается: в месяце то две, то три выплаты
    assert monthly_equivalent(Decimal("10000"), "biweekly") is None
    assert typical_month_amount(Decimal("10000"), "biweekly") == Decimal("20000.00")
    assert typical_month_amount(Decimal("35000"), "monthly") == Decimal("35000.00")
    assert monthly_equivalent(Decimal("120000"), "yearly") == Decimal("10000.00")


def test_semimonthly_dates_and_short_months():
    schedule = Schedule("semimonthly", date(2026, 1, 10), 10, second_day_of_month=25)
    assert pattern_dates(schedule, date(2026, 10, 1), date(2026, 11, 30)) == [
        date(2026, 10, 10),
        date(2026, 10, 25),
        date(2026, 11, 10),
        date(2026, 11, 25),
    ]
    # 15-го и 31-го: в феврале второй день становится последним днём месяца
    month_end_pay = Schedule("semimonthly", date(2026, 1, 15), 15, second_day_of_month=31)
    assert pattern_dates(month_end_pay, date(2026, 2, 1), date(2026, 2, 28)) == [date(2026, 2, 15), date(2026, 2, 28)]
    # 30-го и 31-го в феврале совпадают: одна дата, а не две
    late = Schedule("semimonthly", date(2026, 1, 30), 30, second_day_of_month=31)
    assert pattern_dates(late, date(2026, 2, 1), date(2026, 2, 28)) == [date(2026, 2, 28)]


def test_cycle_boundaries_union_of_incomes():
    assert cycle_boundaries([ADVANCE, SALARY], date(2026, 10, 1), date(2026, 10, 31)) == [
        date(2026, 10, 10),
        date(2026, 10, 25),
    ]
    # Годовые доходы цикл не начинают
    yearly = Schedule("yearly", date(2026, 3, 1))
    assert cycle_boundaries([yearly], date(2026, 1, 1), date(2026, 12, 31)) == []


def test_cycle_containing_between_advance_and_salary():
    schedules = [ADVANCE, SALARY]
    assert cycle_containing(date(2026, 10, 12), schedules) == (date(2026, 10, 10), date(2026, 10, 24))
    # Цикл, начатый зарплатой, заканчивается накануне следующего аванса, уже в другом месяце
    assert cycle_containing(date(2026, 10, 28), schedules) == (date(2026, 10, 25), date(2026, 11, 9))
    assert cycle_containing(date(2026, 10, 3), schedules) == (date(2026, 9, 25), date(2026, 10, 9))
    # Границы включаются
    assert cycle_containing(date(2026, 10, 10), schedules) == (date(2026, 10, 10), date(2026, 10, 24))
    assert cycle_containing(date(2026, 10, 24), schedules) == (date(2026, 10, 10), date(2026, 10, 24))


def test_cycle_without_incomes_is_calendar_month():
    assert cycle_containing(date(2026, 10, 28), []) == (date(2026, 10, 1), date(2026, 10, 31))
    assert cycle_containing(date(2028, 2, 10), []) == (date(2028, 2, 1), date(2028, 2, 29))


def test_single_monthly_income_gives_one_cycle_per_month():
    schedules = [SALARY]
    assert cycle_containing(date(2026, 10, 28), schedules) == (date(2026, 10, 25), date(2026, 11, 24))
    assert cycle_containing(date(2026, 11, 1), schedules) == (date(2026, 10, 25), date(2026, 11, 24))


def test_next_and_previous_cycles_are_adjacent():
    schedules = [ADVANCE, SALARY]
    start, end = cycle_containing(date(2026, 10, 12), schedules)
    assert next_cycle(end, schedules) == (date(2026, 10, 25), date(2026, 11, 9))
    assert previous_cycle(start, schedules) == (date(2026, 9, 25), date(2026, 10, 9))


def test_cycles_cover_every_day_without_gaps():
    """Любые соседние циклы стыкуются: конец одного + 1 день = начало следующего."""
    schedules = [ADVANCE, SALARY]
    day = date(2026, 1, 1)
    start, end = cycle_containing(day, schedules)
    for _ in range(30):
        following = next_cycle(end, schedules)
        assert following[0] == date.fromordinal(end.toordinal() + 1)
        assert following[0] <= following[1]
        end = following[1]
