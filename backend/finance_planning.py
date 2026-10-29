"""Планирование бюджета: бюджетные циклы, баланс обязательных платежей и оценка долговой нагрузки.

Бюджетный цикл (период) — промежуток между двумя поступлениями дохода, а не календарный месяц.
Пример: аванс 10-го и зарплата 25-го дают два цикла в месяц: 10–24 число и 25-е – 9-е следующего месяца.
Для каждого цикла считается: сколько денег придёт, сколько обязательных платежей придётся на этот
промежуток и сколько останется на жизнь. Так видно «кассовый разрыв», когда аренда и кредиты выпали
на один межзарплатный интервал, а соседний остался с запасом.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import and_, exists, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finance_balance import ledger_balance
from finance_format import money, period, short_date
from finance_goals import loan_overview
from finance_recurring import occurrence_rows, sync_recurring
from finance_schedule import (
    Schedule,
    cycle_containing,
    next_cycle,
    previous_cycle,
    typical_month_amount,
)
from finance_services import LedgerAccess, get_ledger_access, list_ledgers, require_manage, summarize_range
from models import (
    FinanceCategory,
    FinanceRecurringOccurrence,
    FinanceRecurringRule,
    FinanceTransaction,
    Ledger,
    User,
)

ZERO = Decimal("0")
CENT = Decimal("0.01")

# Доля обязательных платежей в доходе, выше которой период считается «напряжённым»
TIGHT_SHARE = 0.7

# Доля дохода, на которую можно закладывать обязательные платежи (по правилу банков до 50 %)
SAFE_SHARE = Decimal("0.5")

# Самое большое число периодов в одном ответе
MAX_CYCLES = 12


def set_cycle_mode(db: Session, access: LedgerAccess, mode: str) -> Ledger:
    """Переключает режим бюджетного периода книги (нужны права управления)."""
    require_manage(access)
    access.ledger.cycle_mode = mode
    try:
        db.commit()
        db.refresh(access.ledger)
    except SQLAlchemyError:
        db.rollback()
        raise
    return access.ledger


def cycle_schedules(db: Session, access: LedgerAccess) -> list[Schedule]:
    """Расписания основных доходов, которые задают границы циклов; пусто в календарном режиме.

    Дополнительные доходы границ не задают: период заканчивается датой следующего основного дохода.

    Пример при авансе 10-го и зарплате 25-го: [Schedule("monthly", ..., 10), Schedule("monthly", ..., 25)].
    """
    if access.ledger.cycle_mode != "income":
        return []

    rules = db.scalars(
        select(FinanceRecurringRule)
        .join(FinanceCategory, FinanceCategory.id == FinanceRecurringRule.category_id)
        .where(
            FinanceRecurringRule.ledger_id == access.ledger.id,
            FinanceRecurringRule.is_active.is_(True),
            FinanceRecurringRule.is_primary.is_(True),
            FinanceCategory.kind == "income",
        )
    ).all()
    return [
        Schedule(rule.frequency, rule.start_on, rule.day_of_month, rule.end_on, rule.second_day_of_month)
        for rule in rules
    ]


def period_summary(db: Session, access: LedgerAccess, day: date) -> dict:
    """Итоги бюджетного периода, в который попадает день (месяц или цикл, в зависимости от режима).

    Лимиты категорий в таком отчёте означают «лимит на период»: в календарном режиме на месяц,
    в режиме «от дохода до дохода» на один цикл.
    """
    start, end = cycle_containing(day, cycle_schedules(db, access))
    result = summarize_range(db, access, start, end)
    return {
        "ledger_id": access.ledger.id,
        "start": start,
        "end": end,
        "currency": access.ledger.currency,
        **result,
    }


def _free_transactions_total(db: Session, ledger_id: int, first: date, last: date, kind: str) -> Decimal:
    """Сумма операций вида kind за период, которые НЕ созданы повторяющимися правилами.

    Операции правил относятся к периоду по плановой дате выплаты, а не по дате операции,
    поэтому обычные суммы считаются отдельно, чтобы ничего не посчиталось дважды.
    """
    linked = exists().where(FinanceRecurringOccurrence.transaction_id == FinanceTransaction.id)
    total = db.scalar(
        select(func.coalesce(func.sum(FinanceTransaction.amount), 0))
        .join(FinanceCategory, FinanceCategory.id == FinanceTransaction.category_id)
        .where(
            FinanceTransaction.ledger_id == ledger_id,
            FinanceTransaction.occurred_on >= first,
            FinanceTransaction.occurred_on <= last,
            FinanceCategory.kind == kind,
            ~linked,
        )
    )
    return Decimal(total)


def build_cycle(db: Session, access: LedgerAccess, start: date, end: date, today: date) -> dict:
    """Все числа одного периода [start, end] (оба дня включаются). Формат: CycleResponse.

    Пример для периода 25 окт – 9 ноя при зарплате 90 000 ₽ и обязательных платежах 61 000 ₽:
        income_total=90000, mandatory_total=61000, free_after_mandatory=29000,
        mandatory_share=0.6778, status="ok".
    """
    ledger_id = access.ledger.id
    rows = occurrence_rows(db, ledger_id, start, end, today)

    income_received = _free_transactions_total(db, ledger_id, start, end, "income")
    other_spent = _free_transactions_total(db, ledger_id, start, end, "expense")
    income_expected = ZERO
    mandatory_paid = ZERO
    mandatory_pending = ZERO

    for row in rows:
        if row.status == "skipped":
            continue
        if row.kind == "income":
            if row.status == "posted":
                income_received += row.amount
            else:
                income_expected += row.amount
        else:
            if row.status == "posted":
                mandatory_paid += row.amount
            else:
                mandatory_pending += row.amount

    income_total = income_received + income_expected
    mandatory_total = mandatory_paid + mandatory_pending
    free_after_mandatory = income_total - mandatory_total
    available = free_after_mandatory - other_spent

    is_current = start <= today <= end
    days_total = (end - start).days + 1
    days_left = (end - today).days + 1 if is_current else None

    share = float(mandatory_total / income_total) if income_total > 0 else None

    if mandatory_total > income_total or available < 0:
        status = "gap"
    elif share is not None and share > TIGHT_SHARE:
        status = "tight"
    else:
        status = "ok"

    return {
        "start": start,
        "end": end,
        "is_current": is_current,
        "days_total": days_total,
        "days_left": days_left,
        "income_received": income_received,
        "income_expected": income_expected,
        "income_total": income_total,
        "mandatory_paid": mandatory_paid,
        "mandatory_pending": mandatory_pending,
        "mandatory_total": mandatory_total,
        "other_spent": other_spent,
        "free_after_mandatory": free_after_mandatory,
        "available": available,
        "mandatory_share": round(share, 4) if share is not None else None,
        "status": status,
        "items": [row.as_dict() for row in rows if row.status != "skipped"],
    }


# Как далеко вперёд искать следующий основной доход (годовая зарплата или премия — тоже найдётся)
NEXT_INCOME_HORIZON_DAYS = 400


def _next_primary_income(db: Session, ledger_id: int, today: date) -> date | None:
    """Дата следующего основного дохода, который ещё не подтверждён и не пропущен, начиная с сегодня.

    Подтверждённая («Получено») или пропущенная выплата уже не ждётся, поэтому после подтверждения
    граница переезжает на следующий основной доход. Просроченные неподтверждённые (дата раньше сегодня)
    границей не считаются. Дополнительные доходы границ не задают.
    Пример: зарплата 25-го, сегодня 28 октября, 25 октября подтверждена → date(2026, 11, 25).
    Нет активных основных доходов → None.
    """
    rows = occurrence_rows(db, ledger_id, today, today + timedelta(days=NEXT_INCOME_HORIZON_DAYS), today)
    dates = [row.due_on for row in rows if row.kind == "income" and row.is_primary and row.status == "pending"]
    return min(dates) if dates else None


def spending_plan(db: Session, access: LedgerAccess, today: date) -> dict:
    """Единственный расчёт «Баланс → Свободно → Можно тратить в день» (SpendingPlanResponse).

    Им пользуются и главная (home_overview), и «Финансы → Обзор» (get_cycles), поэтому цифры везде одинаковые.
    Формулы:
      balance         = реальные деньги: подтверждённые операции по сегодня и корректировки (ledger_balance);
      mandatory_due   = неоплаченные обязательные платежи с датой от сегодня до дня перед следующим основным
                        доходом (платёж в день дохода относится к следующему периоду);
      free            = balance − mandatory_due;
      days_left       = дни от сегодня до следующего основного дохода (сегодня считается, день дохода — нет);
      daily_allowance = free ÷ days_left.
    Ожидаемые доходы не входят никуда, пока их не подтвердят.

    Пример: баланс 86 000, следующая зарплата 10 ноября, сегодня 28 октября, аренда 35 000 3 ноября →
        {"balance": 86000, "mandatory_due": 35000, "free": 51000, "next_income_on": date(2026, 11, 10),
         "days_left": 13, "daily_allowance": 3923.08, "status": "ok", "note": None}
    Особые случаи (daily_allowance = None, вместо числа текст в note):
      нет следующего основного дохода → status "no_income", free = None;
      доход ожидается сегодня (0 дней)  → status "income_today";
      free < 0                           → status "gap", «Не хватает N ₽».
    """
    ledger_id = access.ledger.id
    currency = access.ledger.currency
    balance = ledger_balance(db, ledger_id, today)
    next_income = _next_primary_income(db, ledger_id, today)

    plan = {
        "balance": balance,
        "mandatory_due": ZERO,
        "free": None,
        "next_income_on": next_income,
        "days_left": None,
        "daily_allowance": None,
        "status": "ok",
        "note": None,
    }
    if next_income is None:
        plan["status"] = "no_income"
        plan["note"] = "Нет следующего дохода: укажите дату основного дохода в «Платежи и доходы»"
        return plan

    days_left = (next_income - today).days  # 0, если доход ожидается сегодня
    mandatory_due = ZERO
    if days_left > 0:
        rows = occurrence_rows(db, ledger_id, today, next_income - timedelta(days=1), today)
        mandatory_due = sum(
            (row.amount for row in rows if row.kind == "expense" and row.status == "pending"),
            ZERO,
        )
    free = balance - mandatory_due
    plan.update(mandatory_due=mandatory_due, free=free, days_left=days_left)

    if free < 0:
        plan["status"] = "gap"
        plan["note"] = f"Не хватает {money(-free, currency)} до {short_date(next_income)}"
    elif days_left == 0:
        plan["status"] = "income_today"
        plan["note"] = "Основной доход ожидается сегодня: подтвердите поступление"
    else:
        plan["daily_allowance"] = (free / days_left).quantize(CENT)
    return plan


def get_cycles(db: Session, access: LedgerAccess, today: date, previous: int, count: int) -> dict:
    """Текущий период, `previous` предыдущих и всего `count` периодов начиная с текущего, плюс советы.

    Пример: previous=1, count=3 → [прошлый, текущий, следующий, ещё один следующий].
    """
    count = min(max(count, 1), MAX_CYCLES)
    previous = min(max(previous, 0), MAX_CYCLES)
    schedules = cycle_schedules(db, access)

    current = cycle_containing(today, schedules)

    ranges = []
    start = current[0]
    for _ in range(previous):
        start_end = previous_cycle(start, schedules)
        ranges.insert(0, start_end)
        start = start_end[0]

    ranges.append(current)
    end = current[1]
    for _ in range(count - 1):
        following = next_cycle(end, schedules)
        ranges.append(following)
        end = following[1]

    cycles = [build_cycle(db, access, first, last, today) for first, last in ranges]
    upcoming_cycles = [cycle for cycle in cycles if cycle["end"] >= today]
    # «Баланс → Свободно → В день» из общего расчёта: те же цифры, что на главной
    spending = spending_plan(db, access, today)

    return {
        "ledger_id": access.ledger.id,
        "currency": access.ledger.currency,
        "mode": access.ledger.cycle_mode,
        "today": today,
        "spending": spending,
        "cycles": cycles,
        "advice": cycle_advice(db, access, cycles, upcoming_cycles, schedules, spending),
    }


def _advice(code: str, severity: str, text: str) -> dict:
    return {"code": code, "severity": severity, "text": text}


def cycle_advice(
    db: Session,
    access: LedgerAccess,
    cycles: list[dict],
    upcoming_cycles: list[dict],
    schedules: list[Schedule],
    spending: dict,
) -> list[dict]:
    """Короткие советы по периодам, написанные словами. Правила простые и проверяемые:

    1. Просроченные платежи.
    2. Нехватка денег в периоде и, если есть куда, какой платёж можно провести позже.
    3. Неравномерная нагрузка между соседними периодами.
    4. Сколько можно тратить в день до конца текущего периода.
    5. Подсказка включить режим «от дохода до дохода», если доходов два и больше, а режим календарный.
    """
    currency = access.ledger.currency
    advice: list[dict] = []

    overdue = [item for cycle in cycles for item in cycle["items"] if item["overdue"]]
    if overdue:
        names = ", ".join(f"«{item['rule_name']}» ({short_date(item['due_on'])})" for item in overdue[:3])
        extra = f" и ещё {len(overdue) - 3}" if len(overdue) > 3 else ""
        advice.append(
            _advice(
                "overdue",
                "warning",
                f"Есть неотмеченные платежи за прошедшие даты: {names}{extra}. "
                "Отметьте их «Оплачено» или «Пропустить», чтобы расчёты были точными.",
            )
        )

    for index, cycle in enumerate(upcoming_cycles):
        if cycle["status"] != "gap" or cycle["mandatory_total"] <= cycle["income_total"]:
            continue

        label = period(cycle["start"], cycle["end"])
        shortage = cycle["mandatory_total"] - cycle["income_total"]
        text = (
            f"Период {label}: обязательных платежей на {money(cycle['mandatory_total'], currency)}, "
            f"а доходов {money(cycle['income_total'], currency)}. Не хватает {money(shortage, currency)}."
        )

        pending = sorted(
            (item for item in cycle["items"] if item["kind"] == "expense" and item["status"] == "pending"),
            key=lambda item: item["amount"],
            reverse=True,
        )
        following = upcoming_cycles[index + 1] if index + 1 < len(upcoming_cycles) else None

        if pending and following is not None and following["free_after_mandatory"] > 0:
            item = pending[0]
            room = min(item["amount"], following["free_after_mandatory"])
            new_shortage = shortage - room
            if new_shortage <= 0:
                text += (
                    f" Если провести платёж «{item['rule_name']}» ({money(item['amount'], currency)}) "
                    f"после {short_date(following['start'])}, в этом периоде денег хватит."
                )
            else:
                text += (
                    f" Если провести платёж «{item['rule_name']}» после {short_date(following['start'])}, "
                    f"нехватка сократится до {money(new_shortage, currency)}."
                )
        elif following is None or following["free_after_mandatory"] <= 0:
            text += (
                " В соседних периодах свободных денег тоже нет: нужно уменьшить обязательные платежи "
                "или увеличить доход."
            )

        advice.append(_advice("cash_gap", "danger", text))

    for first, second in zip(upcoming_cycles, upcoming_cycles[1:]):
        if first["mandatory_share"] is None or second["mandatory_share"] is None:
            continue
        high, low = sorted((first["mandatory_share"], second["mandatory_share"]), reverse=True)
        if high >= 0.5 and high - low >= 0.4:
            advice.append(
                _advice(
                    "unbalanced",
                    "info",
                    f"Нагрузка распределена неравномерно: в периоде {period(first['start'], first['end'])} "
                    f"обязательные платежи занимают {round(first['mandatory_share'] * 100)} % дохода, "
                    f"в периоде {period(second['start'], second['end'])} — {round(second['mandatory_share'] * 100)} %. "
                    "Если у платежа можно выбрать дату (кредит, рассрочка), перенесите его ближе к менее нагруженному периоду.",
                )
            )
            break

    if spending["daily_allowance"] is not None:
        advice.append(
            _advice(
                "daily_allowance",
                "info",
                f"Из денег на счетах после обязательных платежей до следующего дохода "
                f"({short_date(spending['next_income_on'])}) можно тратить около "
                f"{money(spending['daily_allowance'], currency)} в день.",
            )
        )

    income_rules = db.scalar(
        select(func.count(FinanceRecurringRule.id))
        .join(FinanceCategory, FinanceCategory.id == FinanceRecurringRule.category_id)
        .where(
            FinanceRecurringRule.ledger_id == access.ledger.id,
            FinanceRecurringRule.is_active.is_(True),
            FinanceRecurringRule.is_primary.is_(True),
            FinanceCategory.kind == "income",
        )
    ) or 0
    if access.ledger.cycle_mode == "calendar" and income_rules >= 2:
        advice.append(
            _advice(
                "suggest_income_cycle",
                "info",
                "Доход приходит несколько раз в месяц. Включите бюджетный период «от дохода до дохода»: "
                "тогда крупные платежи не будут смешиваться между авансом и зарплатой.",
            )
        )
    if access.ledger.cycle_mode == "income" and not schedules:
        advice.append(
            _advice(
                "income_cycle_without_income",
                "warning",
                "Режим «от дохода до дохода» включён, но основных регулярных доходов нет: пока периодом служит "
                "календарный месяц. Добавьте аванс или зарплату в повторяющиеся доходы и отметьте их основными.",
            )
        )

    return advice


# ---------------------------------------------------------------------------
# Оценка долговой нагрузки
# ---------------------------------------------------------------------------


def _active_rules(db: Session, ledger_id: int, today: date) -> list[tuple[FinanceRecurringRule, str]]:
    """Действующие правила книги с типом: не на паузе и не закончившиеся к сегодняшнему дню."""
    rows = db.execute(
        select(FinanceRecurringRule, FinanceCategory.kind)
        .join(FinanceCategory, FinanceCategory.id == FinanceRecurringRule.category_id)
        .where(
            FinanceRecurringRule.ledger_id == ledger_id,
            FinanceRecurringRule.is_active.is_(True),
        )
    ).all()
    return [(rule, kind) for rule, kind in rows if rule.end_on is None or rule.end_on >= today]


def _average_monthly_other_expense(db: Session, ledger_id: int, today: date) -> Decimal | None:
    """Средние обычные траты (не обязательные платежи) за последние три полных месяца.

    Берутся только месяцы, в которых вообще были траты. Если трат нет — None.
    Пример: сентябрь 28 000 ₽, август 32 000 ₽ → 30 000 ₽.
    """
    month_first = today.replace(day=1)
    window_start = (month_first - timedelta(days=1)).replace(day=1)
    window_start = (window_start - timedelta(days=1)).replace(day=1)
    window_start = (window_start - timedelta(days=1)).replace(day=1)

    linked = exists().where(FinanceRecurringOccurrence.transaction_id == FinanceTransaction.id)
    month = func.date_trunc("month", FinanceTransaction.occurred_on)
    rows = db.execute(
        select(month, func.sum(FinanceTransaction.amount))
        .join(FinanceCategory, FinanceCategory.id == FinanceTransaction.category_id)
        .where(
            and_(
                FinanceTransaction.ledger_id == ledger_id,
                FinanceTransaction.occurred_on >= window_start,
                FinanceTransaction.occurred_on < month_first,
                FinanceCategory.kind == "expense",
                ~linked,
            )
        )
        .group_by(month)
    ).all()
    if not rows:
        return None
    return (sum((Decimal(total) for _, total in rows), ZERO) / len(rows)).quantize(CENT)


def _status_by_share(share: float | None) -> str:
    """Оценка нагрузки по доле обязательных платежей в доходе (в процентах)."""
    if share is None:
        return "no_income"
    if share < 50:
        return "comfortable"
    if share < 70:
        return "moderate"
    if share < 85:
        return "high"
    return "critical"


def get_load(db: Session, access: LedgerAccess, today: date) -> dict:
    """Оценка нагрузки: хватает ли регулярных доходов на обязательные платежи, и что с этим делать.

    Все суммы приведены к обычному месяцу (выплаты «раз в две недели» считаются как две в месяц, без
    усреднения). Пример для зарплаты 140 000 ₽ и обязательных платежей 100 000 ₽:
        income_monthly=140000, mandatory_monthly=100000, free_monthly=40000,
        mandatory_share=71.4, status="high", safe_extra_payment=0 (по правилу «не более 50 % дохода»).
    """
    currency = access.ledger.currency
    income = ZERO
    mandatory = ZERO
    items: list[dict] = []

    for rule, kind in _active_rules(db, access.ledger.id, today):
        monthly = typical_month_amount(rule.amount, rule.frequency)
        if kind == "income":
            income += monthly
        else:
            mandatory += monthly
            items.append({"name": rule.name, "monthly_amount": monthly})

    items.sort(key=lambda item: item["monthly_amount"], reverse=True)
    free = income - mandatory
    share = round(float(mandatory / income * 100), 1) if income > 0 else None
    status = _status_by_share(share)

    avg_other = _average_monthly_other_expense(db, access.ledger.id, today)
    left_after_expenses = free - avg_other if avg_other is not None else None

    safe_extra = max(income * SAFE_SHARE - mandatory, ZERO)
    if left_after_expenses is not None:
        safe_extra = min(safe_extra, max(left_after_expenses, ZERO))
    safe_extra = safe_extra.quantize(CENT)

    emergency_fund = (mandatory * 3).quantize(CENT)

    advice: list[dict] = []
    if status == "no_income":
        advice.append(
            _advice(
                "no_income",
                "info",
                "Чтобы оценить нагрузку, добавьте регулярные доходы (зарплату, аванс) и обязательные платежи "
                "в разделе «Повторяющиеся».",
            )
        )
    else:
        percent = f"{share:.0f}".replace(".", ",")
        if status in ("high", "critical"):
            advice.append(
                _advice(
                    "no_new_debt",
                    "danger",
                    f"Обязательные платежи занимают {percent} % дохода ({money(mandatory, currency)} из "
                    f"{money(income, currency)}). Новые долги сейчас брать не стоит: свободно остаётся "
                    f"{money(free, currency)} в месяц.",
                )
            )
        elif status == "moderate":
            advice.append(
                _advice(
                    "moderate",
                    "warning",
                    f"Обязательные платежи занимают {percent} % дохода. Новый ежемесячный платёж лучше держать "
                    f"в пределах {money(safe_extra, currency)}.",
                )
            )
        else:
            advice.append(
                _advice(
                    "comfortable",
                    "info",
                    f"Нагрузка комфортная: обязательные платежи занимают {percent} % дохода. "
                    f"Дополнительный платёж до {money(safe_extra, currency)} в месяц не выведет за 50 % дохода.",
                )
            )

        if left_after_expenses is not None and left_after_expenses < 0:
            advice.append(
                _advice(
                    "negative_balance",
                    "danger",
                    f"С учётом обычных трат (в среднем {money(avg_other, currency)} в месяц) расходы превышают "
                    f"доходы на {money(-left_after_expenses, currency)} в месяц.",
                )
            )

        if status in ("moderate", "high", "critical") and items:
            biggest = ", ".join(
                f"«{item['name']}» ({money(item['monthly_amount'], currency)})" for item in items[:3]
            )
            advice.append(
                _advice(
                    "review_biggest",
                    "info",
                    f"Самые крупные обязательные платежи: {biggest}. Пересмотр именно их даст наибольший эффект.",
                )
            )

        loans = loan_overview(db, access.ledger.id)
        if loans and status in ("moderate", "high", "critical"):
            costliest = max(loans, key=lambda loan: loan["rate"] or ZERO)
            advice.append(
                _advice(
                    "costliest_loan",
                    "info",
                    f"Самый дорогой долг: «{costliest['name']}» ({costliest['rate'].normalize():f} % годовых, остаток "
                    f"{money(costliest['remaining'], currency)}). Досрочные платежи по нему сэкономят больше всего.",
                )
            )

        if mandatory > 0:
            advice.append(
                _advice(
                    "emergency_fund",
                    "info",
                    f"Подушка безопасности на три месяца обязательных платежей: {money(emergency_fund, currency)}. "
                    "Создайте для неё цель «Накопить».",
                )
            )

    return {
        "ledger_id": access.ledger.id,
        "currency": currency,
        "income_monthly": income,
        "mandatory_monthly": mandatory,
        "free_monthly": free,
        "mandatory_share": share,
        "status": status,
        "avg_other_expense_monthly": avg_other,
        "left_after_expenses": left_after_expenses,
        "safe_extra_payment": safe_extra,
        "emergency_fund_target": emergency_fund,
        "mandatory_items": items[:8],
        "advice": advice,
    }


def simulate_payment(db: Session, access: LedgerAccess, today: date, payment: Decimal) -> dict:
    """Что будет, если взять новый ежемесячный платёж (кредит, рассрочка).

    Вердикт: ok — доля обязательных платежей остаётся не выше 50 % дохода; risky — до 70 %;
    not_recommended — выше 70 %, либо дохода нет, либо с учётом обычных трат денег не хватит.
    Пример: зарплата 140 000, обязательные 100 000, новый платёж 15 000 → доля 82,1 %, not_recommended.
    """
    currency = access.ledger.currency
    load = get_load(db, access, today)
    income = load["income_monthly"]
    new_mandatory = load["mandatory_monthly"] + payment
    new_free = income - new_mandatory
    new_share = round(float(new_mandatory / income * 100), 1) if income > 0 else None

    over_budget = load["avg_other_expense_monthly"] is not None and new_free - load["avg_other_expense_monthly"] < 0

    if new_share is None or new_share > 70 or over_budget:
        verdict = "not_recommended"
    elif new_share > 50:
        verdict = "risky"
    else:
        verdict = "ok"

    if new_share is None:
        text = "Нет регулярного дохода, поэтому оценить новый платёж нельзя. Добавьте зарплату в «Повторяющиеся»."
    else:
        percent = f"{new_share:.0f}"
        if verdict == "ok":
            text = (
                f"С платежом {money(payment, currency)} обязательные платежи составят {percent} % дохода. "
                f"Свободно останется {money(new_free, currency)} в месяц: это приемлемая нагрузка."
            )
        elif verdict == "risky":
            text = (
                f"С платежом {money(payment, currency)} обязательные платежи составят {percent} % дохода, "
                f"свободно останется {money(new_free, currency)} в месяц. Нагрузка высокая: любое снижение дохода "
                "создаст просрочку."
            )
        else:
            text = (
                f"С платежом {money(payment, currency)} обязательные платежи составят {percent} % дохода, "
                f"свободно останется {money(new_free, currency)} в месяц. Брать этот долг не рекомендуется."
            )
            if over_budget:
                text += " С учётом ваших обычных трат денег в месяц не хватит."
        if verdict != "ok" and load["safe_extra_payment"] > 0:
            text += f" Безопасный размер нового платежа: до {money(load['safe_extra_payment'], currency)} в месяц."

    return {
        "ledger_id": access.ledger.id,
        "currency": currency,
        "payment": payment,
        "income_monthly": income,
        "mandatory_monthly": load["mandatory_monthly"],
        "new_mandatory_monthly": new_mandatory,
        "new_free_monthly": new_free,
        "new_mandatory_share": new_share,
        "verdict": verdict,
        "text": text,
        "advice": load["advice"],
    }


def home_overview(db: Session, user: User, today: date) -> list[dict]:
    """Деньги для главной страницы: по одной записи на каждую книгу пользователя (FinanceHomeLedger).

    Личная и семейная книги считаются отдельно: личные деньги в семейный разрез не входят.
    Все цифры берутся из spending_plan — того же расчёта, что во «Финансы → Обзор».
    Пример: [{"kind": "personal", "total": 86000, "free": 51000, "free_until": date(2026, 11, 10),
              "spending_note": None, ...},
             {"kind": "household", "household_name": "Семья", "total": 0, "free": None, "free_until": None,
              "spending_note": "Нет следующего дохода: ...", ...}]
    """
    result = []
    for ledger in list_ledgers(db, user):
        access = get_ledger_access(db, ledger["id"], user)
        sync_recurring(db, access.ledger.id, today)
        start, end = cycle_containing(today, cycle_schedules(db, access))
        plan = spending_plan(db, access, today)
        result.append(
            {
                "ledger_id": ledger["id"],
                "kind": ledger["kind"],
                "household_id": ledger["household_id"],
                "household_name": ledger["household_name"],
                "currency": ledger["currency"],
                # Баланс-кошелёк: только факты и корректировки
                "total": plan["balance"],
                # Баланс минус платежи до следующего основного дохода; None — дохода нет
                "free": plan["free"],
                "free_until": plan["next_income_on"],
                "spending_status": plan["status"],
                "spending_note": plan["note"],
                "period_start": start,
                "period_end": end,
            }
        )
    return result


__all__ = [
    "build_cycle",
    "get_cycles",
    "get_load",
    "home_overview",
    "period_summary",
    "set_cycle_mode",
    "simulate_payment",
    "spending_plan",
]
