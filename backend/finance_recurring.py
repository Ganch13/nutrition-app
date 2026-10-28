"""Повторяющиеся доходы и обязательные платежи.

Как это работает, на примере:
  1. Пользователь создаёт правило «Аванс 50 000 ₽, каждое 10-е число» (create_rule).
  2. Доход сам не начисляется: с двух дней до плановой даты до двух дней после неё приложение спрашивает
     «Поступил ли платёж?» (income_prompts). Ответ «да» — confirm_occurrence с фактической датой и суммой.
  3. Обязательные платежи с автосписанием создаются при каждом открытии финансов (sync_recurring):
     для дат до сегодняшнего дня без отметки появляются обычные операции. Планировщика задач не нужно.
     Платежи без автосписания ждут нажатия «Оплачено»: confirm_occurrence.
     Выплату можно пропустить (skip_occurrence) или отменить отметку (undo_occurrence).
Отметки хранятся в finance_recurring_occurrences; пара (правило, дата) уникальна, поэтому
одно и то же повторение никогда не превращается в две операции.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finance_errors import (
    FinancePlanError,
    OccurrenceAlreadyHandledError,
    OccurrenceNotDueError,
    OccurrenceNotHandledError,
    RuleCategoryError,
    RuleNotFoundError,
)
from finance_schedule import Schedule, monthly_equivalent, occurrences
from finance_services import FinancePermissionError, LedgerAccess, list_ledgers, transaction_to_dict
from models import (
    FinanceCategory,
    FinanceRecurringOccurrence,
    FinanceRecurringRule,
    FinanceTransaction,
    User,
)
from schemas import OccurrenceConfirm, RecurringRuleCreate, RecurringRuleUpdate, check_rule_schedule

# Как далеко в прошлое автоначисление «догоняет» пропущенные даты (если человек не заходил долго)
MAX_CATCHUP_DAYS = 400

# За сколько дней до плановой даты и сколько дней после неё спрашивать «Поступил ли платёж?».
# Запаса в два дня хватает, чтобы не переносить даты с выходных
PROMPT_WINDOW_DAYS = 2

# Названия категорий, которые создаются при первом использовании, если пользователь не выбрал свою
DEFAULT_INCOME_CATEGORY = "Зарплата"
DEFAULT_EXPENSE_CATEGORY = "Обязательные платежи"


def schedule_of(rule: FinanceRecurringRule) -> Schedule:
    """Расписание правила для функций расчёта дат."""
    return Schedule(
        frequency=rule.frequency,
        start_on=rule.start_on,
        day_of_month=rule.day_of_month,
        end_on=rule.end_on,
        second_day_of_month=rule.second_day_of_month,
    )


def _can_edit(access: LedgerAccess, user: User, rule: FinanceRecurringRule) -> bool:
    """Менять правило может управляющий книгой или его автор."""
    return access.can_manage or rule.created_by_user_id == user.id


def _find_or_create_category(db: Session, ledger_id: int, kind: str) -> FinanceCategory:
    """Категория по умолчанию для правила: «Зарплата» (доход) или «Обязательные платежи» (расход)."""
    name = DEFAULT_INCOME_CATEGORY if kind == "income" else DEFAULT_EXPENSE_CATEGORY
    category = db.scalar(
        select(FinanceCategory).where(
            FinanceCategory.ledger_id == ledger_id,
            FinanceCategory.kind == kind,
            FinanceCategory.name == name,
        )
    )
    if category is None:
        category = FinanceCategory(ledger_id=ledger_id, name=name, kind=kind)
        db.add(category)
        db.flush()
    return category


def _resolve_category(db: Session, access: LedgerAccess, kind: str, category_id: int | None) -> FinanceCategory:
    """Категория правила: указанная (проверяем книгу и тип) или категория по умолчанию."""
    if category_id is None:
        return _find_or_create_category(db, access.ledger.id, kind)
    category = db.get(FinanceCategory, category_id)
    if category is None or category.ledger_id != access.ledger.id or category.kind != kind:
        raise RuleCategoryError("Категория не найдена или относится к другому типу (доход или расход)")
    return category


def get_rule(db: Session, access: LedgerAccess, rule_id: int) -> FinanceRecurringRule:
    """Правило книги; чужое или несуществующее считается ненайденным."""
    rule = db.get(FinanceRecurringRule, rule_id)
    if rule is None or rule.ledger_id != access.ledger.id:
        raise RuleNotFoundError
    return rule


def _handled_dates(db: Session, rule_ids: list[int]) -> dict[int, dict[date, FinanceRecurringOccurrence]]:
    """Все отметки правил: {id правила: {дата: отметка}}."""
    result: dict[int, dict[date, FinanceRecurringOccurrence]] = {rule_id: {} for rule_id in rule_ids}
    if not rule_ids:
        return result
    rows = db.scalars(
        select(FinanceRecurringOccurrence).where(FinanceRecurringOccurrence.rule_id.in_(rule_ids))
    ).all()
    for row in rows:
        result[row.rule_id][row.due_on] = row
    return result


def rule_to_dict(
    db: Session,
    access: LedgerAccess,
    user: User,
    rule: FinanceRecurringRule,
    category: FinanceCategory,
    today: date,
    handled: dict[date, FinanceRecurringOccurrence],
) -> dict:
    """Данные правила для ответа API (RecurringRuleResponse).

    next_due_on — ближайшая дата сегодня или позже, по которой нет отметки; None у закончившегося
    или приостановленного правила.
    """
    next_due = None
    if rule.is_active:
        # Ищем в ближайших двух годах: для обычных частот ближайшая дата находится сразу
        for candidate in occurrences(schedule_of(rule), today, today + timedelta(days=800)):
            if candidate not in handled:
                next_due = candidate
                break

    return {
        "id": rule.id,
        "ledger_id": rule.ledger_id,
        "kind": category.kind,
        "category_id": category.id,
        "category_name": category.name,
        "name": rule.name,
        "amount": rule.amount,
        "frequency": rule.frequency,
        "start_on": rule.start_on,
        "day_of_month": rule.day_of_month,
        "second_day_of_month": rule.second_day_of_month,
        "end_on": rule.end_on,
        "auto_post": rule.auto_post,
        "is_primary": rule.is_primary,
        "is_active": rule.is_active,
        "monthly_amount": monthly_equivalent(rule.amount, rule.frequency),
        "next_due_on": next_due,
        "created_by_user_id": rule.created_by_user_id,
        "can_edit": _can_edit(access, user, rule),
    }


def list_rules(db: Session, access: LedgerAccess, user: User, today: date) -> list[dict]:
    """Все правила книги: сначала доходы, затем платежи; внутри по ближайшей дате.

    Пример элемента: {"id": 1, "kind": "income", "name": "Аванс", "amount": Decimal("50000"),
                      "frequency": "monthly", "next_due_on": date(2026, 11, 10), ...}
    """
    rows = db.execute(
        select(FinanceRecurringRule, FinanceCategory)
        .join(FinanceCategory, FinanceCategory.id == FinanceRecurringRule.category_id)
        .where(FinanceRecurringRule.ledger_id == access.ledger.id)
    ).all()
    handled = _handled_dates(db, [rule.id for rule, _ in rows])

    items = [rule_to_dict(db, access, user, rule, category, today, handled[rule.id]) for rule, category in rows]
    far_future = date.max
    items.sort(key=lambda item: (item["kind"] != "income", item["next_due_on"] or far_future, item["id"]))
    return items


def get_rule_dict(db: Session, access: LedgerAccess, user: User, rule_id: int, today: date) -> dict:
    """Одно правило в формате ответа API (RecurringRuleResponse) с актуальной ближайшей датой."""
    rule = get_rule(db, access, rule_id)
    category = db.get(FinanceCategory, rule.category_id)
    handled = _handled_dates(db, [rule.id])[rule.id]
    return rule_to_dict(db, access, user, rule, category, today, handled)


def create_rule(
    db: Session,
    access: LedgerAccess,
    user: User,
    data: RecurringRuleCreate,
    today: date,
) -> dict:
    """Создаёт правило. Создать может любой, кто имеет доступ к книге.

    Доход никогда не начисляется сам (его подтверждают); платёж списывается сам, только если указан auto_post.
    Основной ли доход (is_primary), решает пользователь; годовой основной доход границ периода не задаёт.
    """
    category = _resolve_category(db, access, data.kind, data.category_id)

    rule = FinanceRecurringRule(
        ledger_id=access.ledger.id,
        category_id=category.id,
        name=data.name,
        amount=data.amount,
        frequency=data.frequency,
        start_on=data.start_on,
        day_of_month=data.day_of_month,
        second_day_of_month=data.second_day_of_month,
        end_on=data.end_on,
        auto_post=bool(data.auto_post) and data.kind == "expense",
        is_primary=data.is_primary,
        is_active=True,
        created_by_user_id=user.id,
    )

    try:
        db.add(rule)
        db.commit()
        db.refresh(rule)
    except SQLAlchemyError:
        db.rollback()
        raise

    return rule_to_dict(db, access, user, rule, category, today, {})


def update_rule(
    db: Session,
    access: LedgerAccess,
    user: User,
    rule_id: int,
    data: RecurringRuleUpdate,
    today: date,
) -> dict:
    """Частично меняет правило (автор правила или управляющий книгой).

    Уже сделанные отметки не трогаются: прошлые операции остаются как были. Новое расписание действует
    для тех дат, по которым отметок ещё нет.
    """
    rule = get_rule(db, access, rule_id)
    if not _can_edit(access, user, rule):
        raise FinancePermissionError

    changes = data.model_dump(exclude_unset=True)
    category = db.get(FinanceCategory, rule.category_id)

    if "category_id" in changes:
        # category_id=null не очищает категорию: оставляем прежнюю
        if changes["category_id"] is not None:
            category = _resolve_category(db, access, category.kind, changes["category_id"])
            rule.category_id = category.id
        changes.pop("category_id")

    for field, value in changes.items():
        setattr(rule, field, value)

    # Согласованность расписания после слияния полей: лишние дни месяца убираются,
    # недостающий первый день берётся из даты начала
    if rule.frequency in ("monthly", "semimonthly"):
        if rule.day_of_month is None:
            rule.day_of_month = rule.start_on.day
    else:
        rule.day_of_month = None
    if rule.frequency != "semimonthly":
        rule.second_day_of_month = None
    try:
        check_rule_schedule(
            category.kind, rule.frequency, rule.day_of_month, rule.second_day_of_month,
            rule.end_on, rule.start_on, rule.auto_post,
        )
    except ValueError as error:
        db.rollback()
        raise FinancePlanError(str(error)) from error

    try:
        db.commit()
        db.refresh(rule)
    except SQLAlchemyError:
        db.rollback()
        raise

    handled = _handled_dates(db, [rule.id])[rule.id]
    return rule_to_dict(db, access, user, rule, category, today, handled)


def delete_rule(db: Session, access: LedgerAccess, user: User, rule_id: int) -> None:
    """Удаляет правило и его отметки. Уже созданные операции остаются обычными операциями."""
    rule = get_rule(db, access, rule_id)
    if not _can_edit(access, user, rule):
        raise FinancePermissionError

    try:
        db.execute(delete(FinanceRecurringOccurrence).where(FinanceRecurringOccurrence.rule_id == rule.id))
        db.delete(rule)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def _new_transaction(
    rule: FinanceRecurringRule,
    category: FinanceCategory,
    amount: Decimal,
    occurred_on: date,
    user_id: int | None,
) -> FinanceTransaction:
    """Операция, созданная по правилу. Название правила попадает в описание операции."""
    return FinanceTransaction(
        ledger_id=rule.ledger_id,
        category_id=category.id,
        amount=amount,
        occurred_on=occurred_on,
        description=rule.name,
        created_by_user_id=user_id,
    )


def sync_recurring(db: Session, ledger_id: int, today: date) -> int:
    """Создаёт операции по платежам с автосписанием за все даты до сегодняшнего дня включительно.

    Доходы здесь не начисляются никогда: их подтверждает человек (см. income_prompts).

    Возвращает, сколько операций создано. Безопасно вызывать сколько угодно раз и одновременно из
    нескольких запросов: повторение, у которого уже есть отметка, пропускается, а вставка отметки
    защищена уникальным ключом (ON CONFLICT DO NOTHING).
    Пример: подписка «каждое 10-е» с автосписанием, сегодня 12 ноября, а в базе операции только
    за октябрь → создаётся одна операция за 10 ноября и возвращается 1.
    """
    rows = db.execute(
        select(FinanceRecurringRule, FinanceCategory)
        .join(FinanceCategory, FinanceCategory.id == FinanceRecurringRule.category_id)
        .where(
            FinanceRecurringRule.ledger_id == ledger_id,
            FinanceRecurringRule.is_active.is_(True),
            FinanceRecurringRule.auto_post.is_(True),
            FinanceCategory.kind == "expense",
        )
    ).all()
    if not rows:
        return 0

    handled = _handled_dates(db, [rule.id for rule, _ in rows])
    created = 0
    window_start = today - timedelta(days=MAX_CATCHUP_DAYS)

    try:
        for rule, category in rows:
            for due in occurrences(schedule_of(rule), window_start, today):
                if due in handled[rule.id]:
                    continue
                # Вставка отметки — «замок» от двойного начисления при одновременных запросах
                occurrence_id = db.execute(
                    pg_insert(FinanceRecurringOccurrence)
                    .values(rule_id=rule.id, due_on=due, status="posted")
                    .on_conflict_do_nothing(constraint="uq_finance_occurrences_rule_due")
                    .returning(FinanceRecurringOccurrence.id)
                ).scalar_one_or_none()
                if occurrence_id is None:
                    continue

                transaction = _new_transaction(rule, category, rule.amount, due, rule.created_by_user_id)
                db.add(transaction)
                db.flush()
                db.execute(
                    update(FinanceRecurringOccurrence)
                    .where(FinanceRecurringOccurrence.id == occurrence_id)
                    .values(transaction_id=transaction.id)
                )
                created += 1
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    return created


def _check_due(rule: FinanceRecurringRule, due_on: date) -> None:
    """Убеждается, что в этот день по правилу действительно есть выплата."""
    if due_on not in occurrences(schedule_of(rule), due_on, due_on):
        raise OccurrenceNotDueError


def confirm_occurrence(
    db: Session,
    access: LedgerAccess,
    user: User,
    rule_id: int,
    due_on: date,
    data: OccurrenceConfirm,
    today: date,
) -> dict:
    """Отмечает выплату состоявшейся и создаёт операцию. Доступно любому участнику книги.

    amount по умолчанию равен плановой сумме правила (можно указать фактическую).
    Дата операции по умолчанию: плановая дата, если она уже прошла, иначе сегодня.
    Возвращает операцию в формате ответа API (FinanceTransactionResponse).
    """
    rule = get_rule(db, access, rule_id)
    _check_due(rule, due_on)

    category = db.get(FinanceCategory, rule.category_id)
    amount = data.amount if data.amount is not None else rule.amount
    occurred_on = data.occurred_on or (due_on if due_on <= today else today)

    try:
        occurrence_id = db.execute(
            pg_insert(FinanceRecurringOccurrence)
            .values(rule_id=rule.id, due_on=due_on, status="posted")
            .on_conflict_do_nothing(constraint="uq_finance_occurrences_rule_due")
            .returning(FinanceRecurringOccurrence.id)
        ).scalar_one_or_none()
        if occurrence_id is None:
            db.rollback()
            raise OccurrenceAlreadyHandledError

        transaction = _new_transaction(rule, category, amount, occurred_on, user.id)
        db.add(transaction)
        db.flush()
        db.execute(
            update(FinanceRecurringOccurrence)
            .where(FinanceRecurringOccurrence.id == occurrence_id)
            .values(transaction_id=transaction.id)
        )
        db.commit()
        db.refresh(transaction)
    except SQLAlchemyError:
        db.rollback()
        raise

    return transaction_to_dict(transaction, category.name, category.kind, user.name)


def skip_occurrence(db: Session, access: LedgerAccess, rule_id: int, due_on: date) -> None:
    """Пропускает выплату: операции не будет, платёж больше не считается ожидаемым."""
    rule = get_rule(db, access, rule_id)
    _check_due(rule, due_on)

    try:
        occurrence_id = db.execute(
            pg_insert(FinanceRecurringOccurrence)
            .values(rule_id=rule.id, due_on=due_on, status="skipped")
            .on_conflict_do_nothing(constraint="uq_finance_occurrences_rule_due")
            .returning(FinanceRecurringOccurrence.id)
        ).scalar_one_or_none()
        if occurrence_id is None:
            db.rollback()
            raise OccurrenceAlreadyHandledError
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def undo_occurrence(db: Session, access: LedgerAccess, user: User, rule_id: int, due_on: date) -> None:
    """Отменяет отметку: выплата снова ожидается, а созданная ею операция удаляется.

    Операцию чужого автора удалить может только управляющий книгой (как и при обычном удалении операции).
    Автоначисляемые доходы после отмены создаются заново при ближайшей проверке: чтобы убрать такой доход
    насовсем, удалите операцию (выплата станет «пропущенной») или приостановите правило.
    """
    rule = get_rule(db, access, rule_id)
    occurrence = db.scalar(
        select(FinanceRecurringOccurrence).where(
            FinanceRecurringOccurrence.rule_id == rule.id,
            FinanceRecurringOccurrence.due_on == due_on,
        )
    )
    if occurrence is None:
        raise OccurrenceNotHandledError

    transaction = None
    if occurrence.transaction_id is not None:
        transaction = db.get(FinanceTransaction, occurrence.transaction_id)
        if transaction is not None and not access.can_manage and transaction.created_by_user_id != user.id:
            raise FinancePermissionError

    try:
        db.delete(occurrence)
        db.flush()
        if transaction is not None:
            db.delete(transaction)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


@dataclass
class OccurrenceRow:
    """Повторение правила с состоянием; из него строится OccurrenceResponse.

    Пример: OccurrenceRow(rule_id=1, rule_name="Аренда", kind="expense", category_name="Обязательные платежи",
                          due_on=date(2026, 11, 3), planned_amount=Decimal("35000"), amount=Decimal("35000"),
                          status="pending", overdue=False, transaction_id=None)
    """

    rule_id: int
    rule_name: str
    kind: str
    category_name: str
    due_on: date
    planned_amount: Decimal
    amount: Decimal
    status: str
    overdue: bool
    transaction_id: int | None
    is_primary: bool = True

    def as_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "kind": self.kind,
            "category_name": self.category_name,
            "due_on": self.due_on,
            "planned_amount": self.planned_amount,
            "amount": self.amount,
            "status": self.status,
            "overdue": self.overdue,
            "transaction_id": self.transaction_id,
            "is_primary": self.is_primary,
        }


def occurrence_rows(
    db: Session,
    ledger_id: int,
    first: date,
    last: date,
    today: date,
) -> list[OccurrenceRow]:
    """Все повторения активных правил книги в промежутке [first, last] с их состоянием.

    Для состоявшихся выплат amount — сумма созданной операции, для остальных плановая сумма.
    Пропущенные тоже возвращаются (status="skipped"): вызывающий код сам решает, показывать ли их.
    Результат отсортирован по дате.
    """
    rows = db.execute(
        select(FinanceRecurringRule, FinanceCategory)
        .join(FinanceCategory, FinanceCategory.id == FinanceRecurringRule.category_id)
        .where(FinanceRecurringRule.ledger_id == ledger_id)
    ).all()
    handled = _handled_dates(db, [rule.id for rule, _ in rows])

    transaction_ids = [
        occurrence.transaction_id
        for per_rule in handled.values()
        for occurrence in per_rule.values()
        if occurrence.transaction_id is not None
    ]
    amounts: dict[int, Decimal] = {}
    if transaction_ids:
        amounts = {
            tx_id: amount
            for tx_id, amount in db.execute(
                select(FinanceTransaction.id, FinanceTransaction.amount).where(
                    FinanceTransaction.id.in_(transaction_ids)
                )
            ).all()
        }

    result: list[OccurrenceRow] = []
    for rule, category in rows:
        if rule.is_active:
            dates = occurrences(schedule_of(rule), first, last)
        else:
            # Правило на паузе новых выплат не ждёт, но прошлые отметки (оплаченное) из истории не исчезают
            dates = [due for due in handled[rule.id] if first <= due <= last]

        for due in dates:
            occurrence = handled[rule.id].get(due)
            if occurrence is None:
                status = "pending"
                amount = rule.amount
                transaction_id = None
            else:
                status = occurrence.status
                transaction_id = occurrence.transaction_id
                amount = amounts.get(transaction_id, rule.amount) if transaction_id else rule.amount

            result.append(
                OccurrenceRow(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    kind=category.kind,
                    category_name=category.name,
                    due_on=due,
                    planned_amount=rule.amount,
                    amount=amount,
                    status=status,
                    overdue=status == "pending" and due < today,
                    transaction_id=transaction_id,
                    is_primary=rule.is_primary,
                )
            )

    result.sort(key=lambda row: (row.due_on, row.rule_id))
    return result


def upcoming(db: Session, access: LedgerAccess, today: date, days: int) -> list[dict]:
    """Просроченные и ближайшие ожидаемые выплаты: от 60 дней назад до today + days.

    Просрочка ищется только за последние 60 дней, чтобы старые забытые даты не засоряли список.
    Пропущенные и отмеченные выплаты в список не входят.
    """
    rows = occurrence_rows(db, access.ledger.id, today - timedelta(days=60), today + timedelta(days=days), today)
    return [row.as_dict() for row in rows if row.status == "pending"]


def income_prompts(db: Session, user: User, today: date) -> list[dict]:
    """Поступления во всех книгах пользователя, о которых пора спросить «Поступил ли платёж?».

    Спрашиваем, пока сегодня не дальше двух дней от плановой даты (с 23 по 27 октября для зарплаты 25-го).
    Отмеченные и пропущенные выплаты, а также правила на паузе в список не попадают.
    Формат элемента — IncomePromptResponse. Пример:
        [{"ledger_id": 1, "ledger_kind": "personal", "rule_name": "Зарплата", "due_on": date(2026, 10, 25), ...}]
    """
    first = today - timedelta(days=PROMPT_WINDOW_DAYS)
    last = today + timedelta(days=PROMPT_WINDOW_DAYS)
    result = []
    for ledger in list_ledgers(db, user):
        for row in occurrence_rows(db, ledger["id"], first, last, today):
            if row.kind != "income" or row.status != "pending":
                continue
            result.append(
                {
                    "ledger_id": ledger["id"],
                    "ledger_kind": ledger["kind"],
                    "household_name": ledger["household_name"],
                    "currency": ledger["currency"],
                    "rule_id": row.rule_id,
                    "rule_name": row.rule_name,
                    "due_on": row.due_on,
                    "planned_amount": row.planned_amount,
                    "is_primary": row.is_primary,
                }
            )
    result.sort(key=lambda item: (item["due_on"], item["ledger_id"], item["rule_id"]))
    return result
