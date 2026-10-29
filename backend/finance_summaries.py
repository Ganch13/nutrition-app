"""Сводные расходы за период (пункт 5 ТЗ от 29.10.2026).

Кроме отдельных покупок можно внести итог за день, неделю, месяц или свои даты: несколько строк
«категория — сумма» за один раз. Каждая строка сохраняется обычной операцией с датой конца периода
и ссылкой на сводку (FinanceTransaction.summary_id), поэтому баланс, отчёты, лимиты и цели
считают её так же, как отдельный расход. Строке можно указать цель — как у обычного расхода.

Сверка. Если за период уже записаны расходы тех же категорий, приложение спрашивает:
«За этот период уже записано 6 400 ₽, сводка на 9 200 ₽. Это дополнение или повтор?»
  * «Добавить как дополнение» — mode="add": ничего не удаляется;
  * «Это повтор, заменить»   — mode="replace": удаляются ровно показанные при сверке операции (replace_ids);
  * «Отмена» — на сервер ничего не уходит.
Сервер сам ничего не складывает и не удаляет: без выбора при пересечении — SummaryOverlapError (409).

В сверку попадают обычные расходы и строки прежних сводок тех же категорий. Не попадают
(и никогда не удаляются заменой): операции повторяющихся платежей и автосписаний, расходы на цели.

Путь данных: форма сводки → POST /finance/ledgers/1/summaries/check → окно сверки →
POST /finance/ledgers/1/summaries {..., "mode": "replace", "replace_ids": [12, 15]} → create_summary.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finance_errors import (
    FinancePlanError,
    RuleCategoryError,
    SummaryNotFoundError,
    SummaryOverlapError,
    SummaryPermissionError,
    SummaryReplaceError,
)
from finance_format import money, period
from finance_goals import link_expense, linked_goal_ids, unlink_expense
from finance_services import DELETED_USER_NAME, LedgerAccess, get_category, transaction_to_dict
from models import (
    FinanceCategory,
    FinanceExpenseSummary,
    FinanceRecurringOccurrence,
    FinanceTransaction,
    FinancialGoalEntry,
    User,
)
from schemas import ExpenseSummaryCheck, ExpenseSummaryCreate

ZERO = Decimal("0")

# Сколько последних сводок отдаёт список
RECENT_SUMMARIES = 50


def _check_period(data: ExpenseSummaryCheck, today: date) -> None:
    """Сводка — только за прошедшее: конец периода не позже сегодня. Пример: сегодня 28.10, конец 31.10 → 422."""
    if data.period_end > today:
        raise FinancePlanError("Сводку можно внести только за прошедшие дни: конец периода не позже сегодня")


def _expense_categories(db: Session, access: LedgerAccess, data: ExpenseSummaryCheck) -> dict[int, FinanceCategory]:
    """Категории строк: {id: категория}. Все должны быть расходными категориями этой книги."""
    result = {}
    for line in data.lines:
        category = get_category(db, access, line.category_id)
        if category.kind != "expense":
            raise RuleCategoryError("В сводке только категории расходов")
        result[category.id] = category
    return result


def _matches(db: Session, access: LedgerAccess, start: date, end: date, category_ids: list[int]) -> list[tuple]:
    """Уже записанные расходы за [start, end] в категориях сводки, которые могут оказаться повтором.

    Возвращает [(операция, название категории), ...] по дате. Операции правил (повторяющиеся платежи,
    автосписания) и расходы на цели не берутся: это не «покупки», их сводка не заменяет.
    Пример: сводка «Продукты» за 20–26 окт → [(Пятёрочка 1 850, "Продукты"), (Рынок 2 600, "Продукты")].
    """
    from_rule = exists().where(FinanceRecurringOccurrence.transaction_id == FinanceTransaction.id)
    to_goal = exists().where(FinancialGoalEntry.transaction_id == FinanceTransaction.id)
    return db.execute(
        select(FinanceTransaction, FinanceCategory.name)
        .join(FinanceCategory, FinanceCategory.id == FinanceTransaction.category_id)
        .where(
            FinanceTransaction.ledger_id == access.ledger.id,
            FinanceTransaction.occurred_on >= start,
            FinanceTransaction.occurred_on <= end,
            FinanceTransaction.category_id.in_(category_ids),
            FinanceCategory.kind == "expense",
            ~from_rule,
            ~to_goal,
        )
        .order_by(FinanceTransaction.occurred_on, FinanceTransaction.id)
    ).all()


def check_summary(db: Session, access: LedgerAccess, data: ExpenseSummaryCheck, today: date) -> dict:
    """Сверка перед сохранением (ExpenseSummaryCheckResponse): ничего не меняет.

    Пример: сводка 9 200 за 20–26 окт, уже записаны «Продукты» 1 850 и 2 600 →
        {"summary_total": 9200, "existing_total": 4450, "existing_count": 2, "matches": [...]}
    """
    _check_period(data, today)
    categories = _expense_categories(db, access, data)
    rows = _matches(db, access, data.period_start, data.period_end, list(categories))
    return {
        "period_start": data.period_start,
        "period_end": data.period_end,
        "summary_total": sum((line.amount for line in data.lines), ZERO),
        "existing_total": sum((transaction.amount for transaction, _ in rows), ZERO),
        "existing_count": len(rows),
        "matches": [
            {
                "transaction_id": transaction.id,
                "occurred_on": transaction.occurred_on,
                "category_id": transaction.category_id,
                "category_name": name,
                "amount": transaction.amount,
                "description": transaction.description,
                "summary_id": transaction.summary_id,
            }
            for transaction, name in rows
        ],
    }


def _can_remove(access: LedgerAccess, user: User, author_id: int | None) -> bool:
    """Свою запись удаляет любой участник, чужую — только управляющий книгой (как у обычных операций)."""
    return access.can_manage or author_id == user.id


def _summary_dict(db: Session, summary: FinanceExpenseSummary, replaced_count: int = 0) -> dict:
    """Сводка со строками в формате ответа API (ExpenseSummaryResponse)."""
    rows = db.execute(
        select(FinanceTransaction, FinanceCategory.name, FinanceCategory.kind)
        .join(FinanceCategory, FinanceCategory.id == FinanceTransaction.category_id)
        .where(FinanceTransaction.summary_id == summary.id)
        .order_by(FinanceTransaction.id)
    ).all()
    goals = linked_goal_ids(db, [transaction.id for transaction, _, _ in rows])
    author = db.get(User, summary.created_by_user_id) if summary.created_by_user_id else None
    author_name = author.name if author else DELETED_USER_NAME
    return {
        "id": summary.id,
        "ledger_id": summary.ledger_id,
        "period_start": summary.period_start,
        "period_end": summary.period_end,
        "note": summary.note,
        "total": sum((transaction.amount for transaction, _, _ in rows), ZERO),
        "created_by_user_id": summary.created_by_user_id,
        "created_by_name": author_name,
        "created_at": summary.created_at,
        "lines": [
            transaction_to_dict(transaction, name, kind, author_name, goals.get(transaction.id), summary)
            for transaction, name, kind in rows
        ],
        "replaced_count": replaced_count,
    }


def _remove_transaction(db: Session, access: LedgerAccess, transaction: FinanceTransaction) -> None:
    """Удаляет операцию; если это был расход на цель — сначала откатывает цель. Без commit."""
    unlink_expense(db, access, transaction.id)
    db.delete(transaction)


def create_summary(db: Session, access: LedgerAccess, user: User, data: ExpenseSummaryCreate, today: date) -> dict:
    """Сохраняет сводку: строки становятся операциями с датой конца периода. Всё одной транзакцией.

    Пересечение с уже записанными расходами (см. _matches):
      * mode не передан → SummaryOverlapError (409) с цифрами, ничего не сохраняется;
      * mode="add" → сводка добавляется, ничего не удаляется;
      * mode="replace" → удаляются только операции из replace_ids, и каждая из них должна быть среди
        найденных сейчас (иначе SummaryReplaceError: данные изменились, нужна новая сверка).
    Пример: строки «Продукты 8 000», «Транспорт 1 200» за 20–26 окт → две операции 26 октября, итог 9 200.
    """
    _check_period(data, today)
    categories = _expense_categories(db, access, data)
    rows = _matches(db, access, data.period_start, data.period_end, list(categories))
    found = {transaction.id: transaction for transaction, _ in rows}

    to_replace: list[FinanceTransaction] = []
    if found and data.mode is None:
        existing = sum((transaction.amount for transaction in found.values()), ZERO)
        total = sum((line.amount for line in data.lines), ZERO)
        currency = access.ledger.currency
        raise SummaryOverlapError(
            f"За {period(data.period_start, data.period_end)} уже записано {money(existing, currency)} "
            f"({len(found)} шт.), сводка на {money(total, currency)}. Это дополнение или повтор?"
        )
    if data.mode == "replace":
        for transaction_id in dict.fromkeys(data.replace_ids):  # без повторов, порядок сохраняется
            transaction = found.get(transaction_id)
            if transaction is None:
                raise SummaryReplaceError
            if not _can_remove(access, user, transaction.created_by_user_id):
                raise SummaryPermissionError
            to_replace.append(transaction)

    summary = FinanceExpenseSummary(
        ledger_id=access.ledger.id,
        period_start=data.period_start,
        period_end=data.period_end,
        note=data.note,
        created_by_user_id=user.id,
    )
    try:
        # Прежние сводки, которые остались без строк после замены, удаляем вместе с ними
        emptied = {transaction.summary_id for transaction in to_replace if transaction.summary_id}
        for transaction in to_replace:
            _remove_transaction(db, access, transaction)
        db.flush()
        for summary_id in emptied:
            if not db.scalar(select(exists().where(FinanceTransaction.summary_id == summary_id))):
                db.delete(db.get(FinanceExpenseSummary, summary_id))

        db.add(summary)
        db.flush()
        for line in data.lines:
            transaction = FinanceTransaction(
                ledger_id=access.ledger.id,
                category_id=line.category_id,
                amount=line.amount,
                occurred_on=data.period_end,
                description=data.note,
                summary_id=summary.id,
                created_by_user_id=user.id,
            )
            db.add(transaction)
            db.flush()
            if line.goal_id is not None:
                link_expense(db, access, line.goal_id, transaction, today)
        db.commit()
        db.refresh(summary)
    except (FinancePlanError, SQLAlchemyError):
        db.rollback()
        raise

    return _summary_dict(db, summary, replaced_count=len(to_replace))


def list_summaries(db: Session, access: LedgerAccess) -> list[dict]:
    """Последние сводки книги (новые периоды сначала) со строками."""
    summaries = db.scalars(
        select(FinanceExpenseSummary)
        .where(FinanceExpenseSummary.ledger_id == access.ledger.id)
        .order_by(FinanceExpenseSummary.period_end.desc(), FinanceExpenseSummary.id.desc())
        .limit(RECENT_SUMMARIES)
    ).all()
    return [_summary_dict(db, summary) for summary in summaries]


def delete_summary(db: Session, access: LedgerAccess, user: User, summary_id: int) -> None:
    """Удаляет сводку целиком: все её строки, а у строк на цели — и записи в целях (цели откатываются).

    Свою сводку удаляет автор, чужую в семейной книге — владелец или администратор.
    """
    summary = db.get(FinanceExpenseSummary, summary_id)
    if summary is None or summary.ledger_id != access.ledger.id:
        raise SummaryNotFoundError
    if not _can_remove(access, user, summary.created_by_user_id):
        raise SummaryPermissionError

    try:
        lines = db.scalars(select(FinanceTransaction).where(FinanceTransaction.summary_id == summary.id)).all()
        for transaction in lines:
            _remove_transaction(db, access, transaction)
        db.flush()
        db.delete(summary)
        db.commit()
    except (FinancePlanError, SQLAlchemyError):
        db.rollback()
        raise


__all__ = ["check_summary", "create_summary", "delete_summary", "list_summaries"]
