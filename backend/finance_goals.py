"""Финансовые цели: накопления, простые долги и кредиты с процентами.

Три механики (формулы из ТЗ):
  savings (накопить): осталось накопить = цель − (стартовый баланс + сумма взносов);
  debt (простой долг): остаток = исходная сумма − (уже выплачено + сумма платежей);
  loan (кредит): с каждым платежом сервер делит его на проценты и тело долга:
      проценты = остаток долга × ставка / 100 / 12
      в тело долга = платёж − проценты
      новый остаток = остаток − в тело долга
      Пример: долг 100 000 ₽ под 60 %, платёж 20 000 ₽ → проценты 5 000 ₽, в тело 15 000 ₽, остаток 85 000 ₽.
Личная цель живёт в личной книге пользователя, совместная в семейной книге: её видят и пополняют
все участники семьи, а доля каждого определяется по автору взноса.
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finance_errors import (
    FinancePlanError,
    GoalClosedError,
    GoalEntryNotFoundError,
    GoalNotFoundError,
    GoalPermissionError,
    PaymentTooLargeError,
)
from finance_format import money
from finance_schedule import Schedule, pattern_dates
from finance_services import DELETED_USER_NAME, LedgerAccess
from models import FinancialGoal, FinancialGoalEntry, User
from schemas import FinanceGoalCreate, FinanceGoalEntryCreate, FinanceGoalUpdate

CENT = Decimal("0.01")
ZERO = Decimal("0")


def money_round(value: Decimal) -> Decimal:
    """Округляет до копеек «по-школьному»: 0,005 → 0,01."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _is_shared(access: LedgerAccess) -> bool:
    return access.ledger.household_id is not None


def _can_edit(access: LedgerAccess, user: User, goal: FinancialGoal) -> bool:
    """Менять и удалять цель может управляющий книгой, а в личной книге всегда её владелец; в семье ещё и автор цели."""
    return access.can_manage or goal.created_by_user_id == user.id


def get_goal(db: Session, access: LedgerAccess, goal_id: int) -> FinancialGoal:
    """Цель книги; чужая или несуществующая считается ненайденной."""
    goal = db.get(FinancialGoal, goal_id)
    if goal is None or goal.ledger_id != access.ledger.id:
        raise GoalNotFoundError
    return goal


def sorted_entries(entries: list[FinancialGoalEntry]) -> list[FinancialGoalEntry]:
    """Взносы в порядке времени: по дате платежа, при равенстве по порядку добавления."""
    return sorted(entries, key=lambda entry: (entry.paid_on, entry.id))


def replay(goal: FinancialGoal, entries: list[FinancialGoalEntry], currency: str = "RUB") -> None:
    """Пересчитывает по порядку проценты, тело долга и остаток во всех взносах цели.

    Для кредита заполняет interest_part / principal_part / balance_after. Для простого долга проверяет,
    что платежи не превышают долг. Накопление не пересчитывается. Если платёж слишком велик,
    выбрасывает PaymentTooLargeError (изменения в базе при этом нужно откатить).
    Вызывается после любого добавления и удаления взноса, потому что проценты зависят от остатка
    на момент платежа, а значит удаление раннего платежа меняет все последующие.
    """
    if goal.kind == "loan":
        balance = goal.target_amount
        rate = goal.interest_rate or ZERO
        for entry in sorted_entries(entries):
            interest = money_round(balance * rate / Decimal(100) / Decimal(12))
            limit = balance + interest
            if entry.amount > limit:
                raise PaymentTooLargeError(
                    f"Платёж больше остатка долга с процентами: не более {money(limit, currency)}"
                )
            principal = entry.amount - interest
            balance = balance - principal
            entry.interest_part = interest
            entry.principal_part = principal
            entry.balance_after = balance
    elif goal.kind == "debt":
        remaining = goal.target_amount - goal.start_amount
        for entry in sorted_entries(entries):
            if entry.amount > remaining:
                raise PaymentTooLargeError(f"Платёж больше остатка долга: не более {money(remaining, currency)}")
            remaining -= entry.amount


def _entries_of(db: Session, goal_ids: list[int]) -> dict[int, list[FinancialGoalEntry]]:
    """Взносы целей: {id цели: [взносы по порядку]}."""
    result: dict[int, list[FinancialGoalEntry]] = {goal_id: [] for goal_id in goal_ids}
    if not goal_ids:
        return result
    rows = db.scalars(select(FinancialGoalEntry).where(FinancialGoalEntry.goal_id.in_(goal_ids))).all()
    for row in rows:
        result[row.goal_id].append(row)
    for goal_id in result:
        result[goal_id] = sorted_entries(result[goal_id])
    return result


def _user_names(db: Session, user_ids: set[int | None]) -> dict[int | None, str]:
    """Имена пользователей: {id: имя}; для пустого id и удалённых аккаунтов «Удалённый пользователь»."""
    names: dict[int | None, str] = {None: DELETED_USER_NAME}
    real_ids = {user_id for user_id in user_ids if user_id is not None}
    if real_ids:
        for user_id, name in db.execute(select(User.id, User.name).where(User.id.in_(real_ids))).all():
            names[user_id] = name
    return names


def goal_numbers(goal: FinancialGoal, entries: list[FinancialGoalEntry]) -> dict:
    """Числа цели: остаток, прогресс, сколько внесено, готова ли.

    Примеры (цель-накопление 200 000, старт 15 000, взносы 20 000 и 5 000):
        {"paid_total": Decimal("40000"), "remaining": Decimal("160000"), "progress": 0.2, "done": False, ...}
    Кредит 100 000 под 60 % после платежа 20 000:
        {"remaining": Decimal("85000"), "last_interest": Decimal("5000"), "interest_paid_total": Decimal("5000"), ...}
    """
    target = goal.target_amount
    total_entries = sum((entry.amount for entry in entries), ZERO)
    last_interest = None
    interest_paid_total = None

    if goal.kind == "loan":
        remaining = entries[-1].balance_after if entries else target
        remaining = remaining if remaining is not None else target
        paid_total = total_entries
        progress_value = (target - remaining) / target
        last_interest = entries[-1].interest_part if entries else None
        interest_paid_total = sum((entry.interest_part or ZERO for entry in entries), ZERO)
        done = remaining <= 0
        remaining = max(remaining, ZERO) if done else remaining
    else:
        paid_total = goal.start_amount + total_entries
        remaining = max(target - paid_total, ZERO)
        progress_value = paid_total / target
        done = paid_total >= target

    progress = float(min(max(progress_value, Decimal(0)), Decimal(1)))
    return {
        "remaining": remaining,
        "paid_total": paid_total,
        "progress": round(progress, 4),
        "done": done,
        "last_interest": last_interest,
        "interest_paid_total": interest_paid_total,
    }


def contributors_of(goal: FinancialGoal, entries: list[FinancialGoalEntry], names: dict[int | None, str]) -> list[dict]:
    """Вклад каждого участника: сколько внёс и какая это доля общей суммы.

    Стартовая сумма (накоплено или уже выплачено до создания цели) записывается автору цели.
    Пример: [{"user_id": 1, "name": "Даня", "total": Decimal("30000"), "share": 0.75},
             {"user_id": 2, "name": "Леся", "total": Decimal("10000"), "share": 0.25}]
    """
    totals: dict[int | None, Decimal] = {}
    if goal.start_amount > 0 and goal.kind != "loan":
        totals[goal.created_by_user_id] = goal.start_amount
    for entry in entries:
        totals[entry.user_id] = totals.get(entry.user_id, ZERO) + entry.amount

    grand_total = sum(totals.values(), ZERO)
    rows = []
    for user_id, total in sorted(totals.items(), key=lambda pair: (-pair[1], pair[0] or 0)):
        rows.append(
            {
                "user_id": user_id,
                "name": names.get(user_id, DELETED_USER_NAME),
                "total": total,
                "share": round(float(total / grand_total), 4) if grand_total > 0 else 0.0,
            }
        )
    return rows


def next_payment_date(payment_day: int, today: date) -> date:
    """Ближайший день ежемесячного платежа не раньше сегодня. Пример: день 15, сегодня 28 октября → 15 ноября."""
    schedule = Schedule("monthly", today, payment_day)
    return pattern_dates(schedule, today, today + timedelta(days=62))[0]


def goal_to_dict(
    access: LedgerAccess,
    user: User,
    goal: FinancialGoal,
    entries: list[FinancialGoalEntry],
    names: dict[int | None, str],
    today: date,
) -> dict:
    """Данные цели для ответа API (FinanceGoalResponse)."""
    numbers = goal_numbers(goal, entries)
    next_payment = None
    if goal.kind == "loan" and goal.payment_day is not None and not numbers["done"]:
        next_payment = next_payment_date(goal.payment_day, today)

    return {
        "id": goal.id,
        "ledger_id": goal.ledger_id,
        "shared": _is_shared(access),
        "kind": goal.kind,
        "name": goal.name,
        "target_amount": goal.target_amount,
        "start_amount": goal.start_amount,
        "interest_rate": goal.interest_rate,
        "payment_day": goal.payment_day,
        "next_payment_on": next_payment,
        "currency": access.ledger.currency,
        "contributors": contributors_of(goal, entries, names),
        "can_edit": _can_edit(access, user, goal),
        "created_by_user_id": goal.created_by_user_id,
        "created_at": goal.created_at,
        **numbers,
    }


def list_goals(db: Session, access: LedgerAccess, user: User, today: date) -> list[dict]:
    """Все цели книги: сначала незавершённые, затем достигнутые; внутри по дате создания."""
    goals = db.scalars(
        select(FinancialGoal).where(FinancialGoal.ledger_id == access.ledger.id).order_by(FinancialGoal.id)
    ).all()
    entries = _entries_of(db, [goal.id for goal in goals])
    user_ids = {goal.created_by_user_id for goal in goals}
    user_ids.update(entry.user_id for items in entries.values() for entry in items)
    names = _user_names(db, user_ids)

    result = [goal_to_dict(access, user, goal, entries[goal.id], names, today) for goal in goals]
    result.sort(key=lambda item: (item["done"], item["id"]))
    return result


def get_goal_detail(db: Session, access: LedgerAccess, user: User, goal_id: int, today: date) -> dict:
    """Цель с историей взносов (новые сверху)."""
    goal = get_goal(db, access, goal_id)
    entries = _entries_of(db, [goal.id])[goal.id]
    names = _user_names(db, {goal.created_by_user_id, *(entry.user_id for entry in entries)})

    can_edit = _can_edit(access, user, goal)
    history = [
        {
            "id": entry.id,
            "goal_id": goal.id,
            "user_id": entry.user_id,
            "user_name": names.get(entry.user_id, DELETED_USER_NAME),
            "paid_on": entry.paid_on,
            "amount": entry.amount,
            "interest_part": entry.interest_part,
            "principal_part": entry.principal_part,
            "balance_after": entry.balance_after,
            "note": entry.note,
            "can_delete": can_edit or entry.user_id == user.id,
        }
        for entry in reversed(entries)
    ]
    return {**goal_to_dict(access, user, goal, entries, names, today), "entries": history}


def create_goal(db: Session, access: LedgerAccess, user: User, data: FinanceGoalCreate, today: date) -> dict:
    """Создаёт цель в книге из адреса запроса. Создать может любой, кто имеет доступ к книге."""
    goal = FinancialGoal(
        ledger_id=access.ledger.id,
        kind=data.kind,
        name=data.name,
        target_amount=data.target_amount,
        start_amount=data.start_amount,
        interest_rate=data.interest_rate,
        payment_day=data.payment_day,
        created_by_user_id=user.id,
    )
    try:
        db.add(goal)
        db.commit()
        db.refresh(goal)
    except SQLAlchemyError:
        db.rollback()
        raise

    return goal_to_dict(access, user, goal, [], {user.id: user.name, None: DELETED_USER_NAME}, today)


def update_goal(
    db: Session,
    access: LedgerAccess,
    user: User,
    goal_id: int,
    data: FinanceGoalUpdate,
    today: date,
) -> dict:
    """Частично меняет цель и пересчитывает проценты во всех взносах (автор цели или управляющий)."""
    goal = get_goal(db, access, goal_id)
    if not _can_edit(access, user, goal):
        raise GoalPermissionError

    changes = data.model_dump(exclude_unset=True)
    if goal.kind == "loan":
        if changes.get("start_amount"):
            raise FinancePlanError("У кредита нет «уже выплачено»: измените текущий основной долг")
        changes.pop("start_amount", None)
        if changes.get("interest_rate", 0) is None or changes.get("payment_day", 0) is None:
            raise FinancePlanError("У кредита ставка и день платежа обязательны")
    elif "interest_rate" in changes or "payment_day" in changes:
        if changes.get("interest_rate") is not None or changes.get("payment_day") is not None:
            raise FinancePlanError("Ставка и день платежа есть только у кредита")
        changes.pop("interest_rate", None)
        changes.pop("payment_day", None)

    for field, value in changes.items():
        setattr(goal, field, value)

    if goal.kind == "debt" and goal.start_amount > goal.target_amount:
        db.rollback()
        raise FinancePlanError("Выплачено не может быть больше суммы долга")

    entries = _entries_of(db, [goal.id])[goal.id]
    try:
        replay(goal, entries, access.ledger.currency)
        db.commit()
        db.refresh(goal)
    except PaymentTooLargeError:
        db.rollback()
        raise PaymentTooLargeError("Изменение невозможно: уже внесённые платежи не помещаются в новую сумму") from None
    except SQLAlchemyError:
        db.rollback()
        raise

    entries = _entries_of(db, [goal.id])[goal.id]
    names = _user_names(db, {goal.created_by_user_id, *(entry.user_id for entry in entries)})
    return goal_to_dict(access, user, goal, entries, names, today)


def delete_goal(db: Session, access: LedgerAccess, user: User, goal_id: int) -> None:
    """Удаляет цель вместе с историей взносов (автор цели или управляющий)."""
    goal = get_goal(db, access, goal_id)
    if not _can_edit(access, user, goal):
        raise GoalPermissionError

    try:
        for entry in _entries_of(db, [goal.id])[goal.id]:
            db.delete(entry)
        db.flush()
        db.delete(goal)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def add_entry(
    db: Session,
    access: LedgerAccess,
    user: User,
    goal_id: int,
    data: FinanceGoalEntryCreate,
    today: date,
) -> dict:
    """Добавляет взнос или платёж; для кредита сразу делит его на проценты и тело долга.

    Дата платежа не может быть в будущем. В достигнутый долг или кредит платить нельзя
    (накопление можно пополнять и после достижения цели).
    Возвращает цель с историей (FinanceGoalDetailResponse), чтобы интерфейс сразу обновился.
    """
    goal = get_goal(db, access, goal_id)
    paid_on = data.paid_on or today
    if paid_on > today:
        raise FinancePlanError("Дата платежа не может быть в будущем")

    entries = _entries_of(db, [goal.id])[goal.id]
    if goal.kind != "savings" and goal_numbers(goal, entries)["done"]:
        raise GoalClosedError

    entry = FinancialGoalEntry(
        goal_id=goal.id,
        user_id=user.id,
        paid_on=paid_on,
        amount=data.amount,
        note=data.note,
    )

    try:
        db.add(entry)
        db.flush()
        replay(goal, [*entries, entry], access.ledger.currency)
        db.commit()
    except PaymentTooLargeError:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        raise

    return get_goal_detail(db, access, user, goal.id, today)


def delete_entry(
    db: Session,
    access: LedgerAccess,
    user: User,
    goal_id: int,
    entry_id: int,
    today: date,
) -> dict:
    """Удаляет взнос (свой или любой, если пользователь управляет целью) и пересчитывает остаток."""
    goal = get_goal(db, access, goal_id)
    entry = db.get(FinancialGoalEntry, entry_id)
    if entry is None or entry.goal_id != goal.id:
        raise GoalEntryNotFoundError
    if not (_can_edit(access, user, goal) or entry.user_id == user.id):
        raise GoalPermissionError

    try:
        db.delete(entry)
        db.flush()
        replay(goal, _entries_of(db, [goal.id])[goal.id], access.ledger.currency)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    return get_goal_detail(db, access, user, goal.id, today)


def loan_overview(db: Session, ledger_id: int) -> list[dict]:
    """Непогашенные кредиты книги: название, ставка и остаток. Нужны для советов по нагрузке.

    Пример: [{"name": "Кредит в банке", "rate": Decimal("60"), "remaining": Decimal("85000")}].
    """
    goals = db.scalars(
        select(FinancialGoal).where(FinancialGoal.ledger_id == ledger_id, FinancialGoal.kind == "loan")
    ).all()
    entries = _entries_of(db, [goal.id for goal in goals])
    result = []
    for goal in goals:
        numbers = goal_numbers(goal, entries[goal.id])
        if not numbers["done"]:
            result.append({"name": goal.name, "rate": goal.interest_rate, "remaining": numbers["remaining"]})
    return result
