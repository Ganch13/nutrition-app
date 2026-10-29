"""Операции (доходы и расходы): создание, изменение и удаление вместе со связью «расход → цель».

Пункт 2 ТЗ от 29.10.2026: расход можно отнести к цели (накопление, долг, кредит этой же книги).
Тогда сервер сам ведёт запись в истории цели:
  * создание расхода с goal_id → в цели появляется запись на ту же сумму и дату;
  * изменение расхода (сумма, дата, цель) → запись пересоздаётся, цель пересчитывается;
  * удаление расхода → запись исчезает, цель откатывается.
Операция и запись сохраняются одной транзакцией базы: если цель не принимает платёж
(например, он больше остатка долга), не сохраняется и сама операция.

Путь данных: браузер → POST /finance/ledgers/1/transactions {"amount": 5000, "goal_id": 3, ...}
→ create_transaction → FinanceTransaction + FinancialGoalEntry(transaction_id=...) → commit.
"""

from datetime import date

from sqlalchemy import exists, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finance_errors import FinancePlanError, GoalNeedsExpenseError
from finance_goals import link_expense, linked_goal_ids, unlink_expense
from finance_services import (
    FinancePermissionError,
    LedgerAccess,
    TransactionNotFoundError,
    get_category,
    transaction_to_dict,
)
from models import FinanceExpenseSummary, FinanceRecurringOccurrence, FinanceTransaction, User
from schemas import FinanceTransactionCreate, FinanceTransactionUpdate


def _get_own_transaction(db: Session, access: LedgerAccess, user: User, transaction_id: int) -> FinanceTransaction:
    """Операция книги, которую пользователю можно менять: свою — любой участник, чужую — только управляющий.

    Операция другой книги считается несуществующей (TransactionNotFoundError → 404).
    """
    transaction = db.get(FinanceTransaction, transaction_id)
    if transaction is None or transaction.ledger_id != access.ledger.id:
        raise TransactionNotFoundError
    if not access.can_manage and transaction.created_by_user_id != user.id:
        raise FinancePermissionError
    return transaction


def _response(db: Session, transaction: FinanceTransaction, category, author_name: str | None) -> dict:
    """Операция в формате ответа API вместе с её целью и сводкой (FinanceTransactionResponse)."""
    goal = linked_goal_ids(db, [transaction.id]).get(transaction.id)
    summary = db.get(FinanceExpenseSummary, transaction.summary_id) if transaction.summary_id else None
    return transaction_to_dict(transaction, category.name, category.kind, author_name, goal, summary)


def create_transaction(
    db: Session,
    access: LedgerAccess,
    user: User,
    data: FinanceTransactionCreate,
    today: date,
) -> dict:
    """Добавляет операцию (доступно любому участнику книги); с goal_id — ещё и запись в цели.

    Пример: {"category_id": 9, "amount": 5000, "occurred_on": "2026-10-28", "goal_id": 3}
    → операция 5 000 ₽ и запись в цели «Отпуск» на 5 000 ₽ от 28 октября.
    Цель только у расхода (иначе 422) и только из этой же книги (иначе 404).
    """
    category = get_category(db, access, data.category_id)
    if data.goal_id is not None and category.kind != "expense":
        raise GoalNeedsExpenseError

    transaction = FinanceTransaction(
        ledger_id=access.ledger.id,
        category_id=category.id,
        amount=data.amount,
        occurred_on=data.occurred_on,
        description=data.description,
        created_by_user_id=user.id,
    )
    try:
        db.add(transaction)
        db.flush()  # нужен transaction.id для записи в цели
        if data.goal_id is not None:
            link_expense(db, access, data.goal_id, transaction, today)
        db.commit()
        db.refresh(transaction)
    except (FinancePlanError, SQLAlchemyError):
        # Цель не приняла платёж или ошибка базы: не сохраняем ни операцию, ни запись
        db.rollback()
        raise

    return _response(db, transaction, category, user.name)


def update_transaction(
    db: Session,
    access: LedgerAccess,
    user: User,
    transaction_id: int,
    data: FinanceTransactionUpdate,
    today: date,
) -> dict:
    """Меняет операцию и её запись в цели. Права как на удаление: свою — любой, чужую — управляющий.

    Передаются только меняемые поля. Цель:
      * поле goal_id не передано — остаётся прежняя цель (запись пересчитается под новую сумму или дату);
      * goal_id = 2 — перенести на другую цель;
      * goal_id = null — отвязать от цели (запись из цели уйдёт, расход останется).
    Пример: расход 5 000 на «Отпуск», PATCH {"amount": 3000} → в «Отпуске» накоплено на 2 000 меньше.
    """
    transaction = _get_own_transaction(db, access, user, transaction_id)
    changes = data.model_dump(exclude_unset=True)

    # Какая цель будет после изменения: новая из запроса или прежняя
    current_goal = linked_goal_ids(db, [transaction.id]).get(transaction.id)
    goal_id = changes.pop("goal_id") if "goal_id" in changes else (current_goal[0] if current_goal else None)

    category = get_category(db, access, changes.get("category_id", transaction.category_id))
    if goal_id is not None and category.kind != "expense":
        raise GoalNeedsExpenseError

    try:
        # Старую запись убираем, потом создаём заново с новыми суммой, датой и целью:
        # так проценты кредита и остаток долга пересчитываются по правилам replay
        unlink_expense(db, access, transaction.id)
        for field, value in changes.items():
            setattr(transaction, field, value)
        db.flush()
        if goal_id is not None:
            link_expense(db, access, goal_id, transaction, today)
        db.commit()
        db.refresh(transaction)
    except (FinancePlanError, SQLAlchemyError):
        db.rollback()
        raise

    author = db.get(User, transaction.created_by_user_id) if transaction.created_by_user_id else None
    return _response(db, transaction, category, author.name if author else None)


def delete_transaction(db: Session, access: LedgerAccess, user: User, transaction_id: int) -> None:
    """Удаляет операцию: свою может любой участник, чужую только управляющий.

    Если расход был отнесён к цели, его запись уходит из цели, и цель пересчитывается
    (у накопления прогресс уменьшается, у долга остаток снова растёт).
    """
    transaction = _get_own_transaction(db, access, user, transaction_id)

    try:
        unlink_expense(db, access, transaction.id)
        # Если операцию создало повторяющееся правило, отметка не пропадает, а становится «пропущено»:
        # иначе правило со следующей проверкой создало бы такую же операцию заново
        db.execute(
            update(FinanceRecurringOccurrence)
            .where(FinanceRecurringOccurrence.transaction_id == transaction.id)
            .values(status="skipped", transaction_id=None)
        )
        summary_id = transaction.summary_id
        db.delete(transaction)
        db.flush()
        # Удалили последнюю строку сводки — пустая сводка больше не нужна
        if summary_id is not None:
            has_lines = db.scalar(select(exists().where(FinanceTransaction.summary_id == summary_id)))
            if not has_lines:
                db.delete(db.get(FinanceExpenseSummary, summary_id))
        db.commit()
    except (FinancePlanError, SQLAlchemyError):
        db.rollback()
        raise


__all__ = ["create_transaction", "delete_transaction", "update_transaction"]
