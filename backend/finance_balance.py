"""Баланс книги («Всего» на главной) и корректировки баланса.

Баланс — это кошелёк: сколько денег есть на самом деле. В него входят только факты:
  * операции с датой по сегодняшний день включительно — обычные траты, подтверждённые «Получено»
    доходы, оплаченные платежи и автосписания (автосписание считается фактом в день платежа);
  * корректировки баланса — «на счетах на самом деле столько-то».
Не входят: ожидаемые доходы, ещё не оплаченные платежи и операции с будущей датой.

Корректировка нужна, когда цифра в приложении разошлась с банком, а заводить фиктивный доход
или расход не хочется: отчёты о доходах и расходах она не меняет.
Пример: насчитано 50 000 ₽, человек вводит «на самом деле 52 300 ₽» → сохраняется +2 300 ₽,
и «Всего» становится 52 300 ₽, а траты за месяц остаются прежними.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finance_errors import (
    AdjustmentNotFoundError,
    AdjustmentPermissionError,
    BalanceUnchangedError,
    FinancePlanError,
)
from finance_services import DELETED_USER_NAME, LedgerAccess
from models import FinanceBalanceAdjustment, FinanceCategory, FinanceTransaction, User
from schemas import BalanceSet

# Сколько последних корректировок показывать вместе с балансом
RECENT_ADJUSTMENTS = 20

# Самая большая разница, которая помещается в колонку Numeric(12, 2)
MAX_ADJUSTMENT = Decimal("9999999999.99")


def ledger_balance(db: Session, ledger_id: int, today: date) -> Decimal:
    """Баланс книги на сегодня: фактические операции плюс корректировки (см. описание модуля).

    Пример: доходов за всё время 280 000 ₽, расходов 231 500 ₽, корректировка +2 300 ₽ → Decimal("50800").
    Операция или корректировка с датой позже today не учитывается.
    """
    signed = func.sum(
        case(
            (FinanceCategory.kind == "income", FinanceTransaction.amount),
            else_=-FinanceTransaction.amount,
        )
    )
    operations = db.scalar(
        select(func.coalesce(signed, 0))
        .join(FinanceCategory, FinanceCategory.id == FinanceTransaction.category_id)
        .where(FinanceTransaction.ledger_id == ledger_id, FinanceTransaction.occurred_on <= today)
    )
    return Decimal(operations) + _adjustments_total(db, ledger_id, today)


def _adjustments_total(db: Session, ledger_id: int, today: date) -> Decimal:
    """Сумма корректировок книги по сегодняшний день. Пример: +2 300 и −500 → Decimal("1800")."""
    total = db.scalar(
        select(func.coalesce(func.sum(FinanceBalanceAdjustment.amount), 0)).where(
            FinanceBalanceAdjustment.ledger_id == ledger_id,
            FinanceBalanceAdjustment.adjusted_on <= today,
        )
    )
    return Decimal(total)


def adjustment_to_dict(adjustment: FinanceBalanceAdjustment, author_name: str | None) -> dict:
    """Корректировка в формате ответа API (BalanceAdjustmentResponse).

    Пример: {"id": 4, "amount": Decimal("2300.00"), "adjusted_on": date(2026, 10, 29),
             "note": "сверка с банком", "created_by_user_id": 1, "created_by_name": "Даня", ...}
    Если автор удалил аккаунт, имя заменяется на «Удалённый пользователь».
    """
    return {
        "id": adjustment.id,
        "amount": adjustment.amount,
        "adjusted_on": adjustment.adjusted_on,
        "note": adjustment.note,
        "created_by_user_id": adjustment.created_by_user_id,
        "created_by_name": author_name or DELETED_USER_NAME,
        "created_at": adjustment.created_at,
    }


def get_balance(db: Session, access: LedgerAccess, today: date) -> dict:
    """Баланс книги и последние корректировки (LedgerBalanceResponse).

    Пример: {"ledger_id": 1, "currency": "RUB", "total": Decimal("52300"),
             "adjustments_total": Decimal("2300"), "adjustments": [{...}]}
    """
    ledger = access.ledger
    rows = db.execute(
        select(FinanceBalanceAdjustment, User.name)
        .outerjoin(User, User.id == FinanceBalanceAdjustment.created_by_user_id)
        .where(FinanceBalanceAdjustment.ledger_id == ledger.id)
        .order_by(FinanceBalanceAdjustment.adjusted_on.desc(), FinanceBalanceAdjustment.id.desc())
        .limit(RECENT_ADJUSTMENTS)
    ).all()
    return {
        "ledger_id": ledger.id,
        "currency": ledger.currency,
        "total": ledger_balance(db, ledger.id, today),
        "adjustments_total": _adjustments_total(db, ledger.id, today),
        "adjustments": [adjustment_to_dict(adjustment, name) for adjustment, name in rows],
    }


def set_actual_balance(db: Session, access: LedgerAccess, user: User, data: BalanceSet, today: date) -> dict:
    """Запоминает фактический остаток: сохраняет разницу с текущим балансом как корректировку.

    Доступно любому участнику книги (как и запись обычной траты); в истории видно, кто сверял.
    Пример: баланс 50 000, data.actual = 52 300 → корректировка +2 300 на сегодня; ответ — get_balance,
    где total = 52 300. Если разницы нет — BalanceUnchangedError (422).
    """
    current = ledger_balance(db, access.ledger.id, today)  # например Decimal("50000.00")
    delta = data.actual - current                          # например Decimal("2300.00")
    if delta == 0:
        raise BalanceUnchangedError
    if abs(delta) > MAX_ADJUSTMENT:
        raise FinancePlanError("Слишком большая разница с текущим балансом")

    db.add(
        FinanceBalanceAdjustment(
            ledger_id=access.ledger.id,
            amount=delta,
            adjusted_on=today,
            note=data.note,
            created_by_user_id=user.id,
        )
    )
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return get_balance(db, access, today)


def delete_adjustment(db: Session, access: LedgerAccess, user: User, adjustment_id: int, today: date) -> dict:
    """Удаляет корректировку (баланс возвращается к прежней цифре) и возвращает обновлённый баланс.

    Свою корректировку может удалить автор; чужую в семейной книге — владелец или администратор семьи.
    Корректировка другой книги считается несуществующей (404), чтобы не выдавать чужие данные.
    """
    adjustment = db.get(FinanceBalanceAdjustment, adjustment_id)
    if adjustment is None or adjustment.ledger_id != access.ledger.id:
        raise AdjustmentNotFoundError
    if not access.can_manage and adjustment.created_by_user_id != user.id:
        raise AdjustmentPermissionError

    try:
        db.delete(adjustment)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return get_balance(db, access, today)


__all__ = [
    "delete_adjustment",
    "get_balance",
    "ledger_balance",
    "set_actual_balance",
]
