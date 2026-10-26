"""Бизнес-логика финансов: книги, категории, операции, лимиты и сводка."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from models import (
    FinanceBudget,
    FinanceCategory,
    FinanceTransaction,
    Household,
    HouseholdMember,
    Ledger,
    User,
)
from schemas import FinanceCategoryCreate, FinanceTransactionCreate, LedgerCreate

# Категории, которые создаются вместе с книгой
DEFAULT_EXPENSE_CATEGORIES = [
    "Продукты",
    "Жильё и коммунальные",
    "Транспорт",
    "Здоровье",
    "Спорт",
    "Развлечения",
    "Одежда",
    "Образование",
    "Другое",
]
DEFAULT_INCOME_CATEGORIES = ["Зарплата", "Прочие доходы"]

# Роли домохозяйства, которым разрешено управлять категориями и лимитами
MANAGER_ROLES = ("owner", "admin")


class LedgerNotFoundError(Exception):
    """Книги нет или у пользователя нет к ней доступа (причину не раскрываем)."""


class FinanceHouseholdNotFoundError(Exception):
    """Домохозяйство не найдено или пользователь в нём не состоит."""


class FinancePermissionError(Exception):
    """Доступ к книге есть, но для этого действия не хватает прав."""


class LedgerAlreadyExistsError(Exception):
    """Книга для этого владельца уже создана."""


class CategoryNotFoundError(Exception):
    """Категории нет в этой книге."""


class CategoryAlreadyExistsError(Exception):
    """Категория с таким названием и типом уже есть."""


class CategoryInUseError(Exception):
    """В категории есть операции, удалить её нельзя."""


class TransactionNotFoundError(Exception):
    """Операции нет в этой книге."""


class BudgetCategoryError(Exception):
    """Лимит можно задать только для категории расходов."""


@dataclass
class LedgerAccess:
    """Результат проверки доступа: книга и право управлять ею."""

    ledger: Ledger
    can_manage: bool


def get_ledger_access(db: Session, ledger_id: int, user: User) -> LedgerAccess:
    """Проверяет, что пользователь имеет доступ к книге, и возвращает его права.

    Личная книга: доступна только владельцу, он может всё.
    Семейная книга: доступна участникам домохозяйства; управлять могут owner и admin.
    Для недоступной книги всегда LedgerNotFoundError (как будто её нет).
    """
    ledger = db.get(Ledger, ledger_id)

    if ledger is None:
        raise LedgerNotFoundError

    if ledger.user_id is not None:
        if ledger.user_id != user.id:
            raise LedgerNotFoundError
        return LedgerAccess(ledger=ledger, can_manage=True)

    membership = db.get(HouseholdMember, (ledger.household_id, user.id))

    if membership is None:
        raise LedgerNotFoundError

    return LedgerAccess(ledger=ledger, can_manage=membership.role in MANAGER_ROLES)


def require_manage(access: LedgerAccess) -> None:
    """Выбрасывает FinancePermissionError, если пользователь не может управлять книгой."""
    if not access.can_manage:
        raise FinancePermissionError


def ledger_to_dict(ledger: Ledger, household_name: str | None, can_manage: bool) -> dict:
    """Собирает данные книги для ответа API (LedgerResponse)."""
    return {
        "id": ledger.id,
        "kind": "personal" if ledger.user_id is not None else "household",
        "household_id": ledger.household_id,
        "household_name": household_name,
        "currency": ledger.currency,
        "can_manage": can_manage,
    }


def transaction_to_dict(
    transaction: FinanceTransaction,
    category_name: str,
    kind: str,
    author_name: str,
) -> dict:
    """Собирает данные операции для ответа API (FinanceTransactionResponse)."""
    return {
        "id": transaction.id,
        "ledger_id": transaction.ledger_id,
        "category_id": transaction.category_id,
        "category_name": category_name,
        "kind": kind,
        "amount": transaction.amount,
        "occurred_on": transaction.occurred_on,
        "description": transaction.description,
        "created_by_user_id": transaction.created_by_user_id,
        "created_by_name": author_name,
        "created_at": transaction.created_at,
    }


def month_bounds(month: str) -> tuple[date, date]:
    """Границы месяца: "2026-10" → (2026-10-01, 2026-11-01); конец не включается."""
    year, month_number = (int(part) for part in month.split("-"))
    first_day = date(year, month_number, 1)

    if month_number == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month_number + 1, 1)

    return first_day, next_month


def list_ledgers(db: Session, user: User) -> list[dict]:
    """Возвращает книги пользователя: личную (если есть) и семейные его домохозяйств.

    Личная книга идёт первой. Результат, например:
        [{"id": 1, "kind": "personal", "currency": "EUR", "can_manage": True, ...},
         {"id": 2, "kind": "household", "household_name": "Семья", "can_manage": False, ...}]
    """
    statement = (
        select(Ledger, Household.name, HouseholdMember.role)
        .select_from(Ledger)
        .outerjoin(Household, Household.id == Ledger.household_id)
        .outerjoin(
            HouseholdMember,
            and_(
                HouseholdMember.household_id == Ledger.household_id,
                HouseholdMember.user_id == user.id,
            ),
        )
        .where(or_(Ledger.user_id == user.id, HouseholdMember.user_id == user.id))
        # Личные книги (user_id не пустой) первыми
        .order_by(Ledger.user_id.is_(None), Ledger.id)
    )

    result = []
    for ledger, household_name, role in db.execute(statement).all():
        can_manage = ledger.user_id is not None or role in MANAGER_ROLES
        result.append(ledger_to_dict(ledger, household_name, can_manage))

    return result


def create_ledger(db: Session, user: User, data: LedgerCreate) -> dict:
    """Создаёт личную или семейную книгу вместе с категориями по умолчанию."""
    household_name = None

    if data.kind == "personal":
        if db.scalar(select(Ledger).where(Ledger.user_id == user.id)) is not None:
            raise LedgerAlreadyExistsError

        ledger = Ledger(user_id=user.id, currency=data.currency)
    else:
        household = db.get(Household, data.household_id)
        membership = db.get(HouseholdMember, (data.household_id, user.id))

        if household is None or membership is None:
            raise FinanceHouseholdNotFoundError

        if membership.role not in MANAGER_ROLES:
            raise FinancePermissionError

        if db.scalar(select(Ledger).where(Ledger.household_id == data.household_id)) is not None:
            raise LedgerAlreadyExistsError

        ledger = Ledger(household_id=data.household_id, currency=data.currency)
        household_name = household.name

    try:
        db.add(ledger)
        # flush отправляет INSERT, чтобы получить ledger.id, но транзакцию не завершает
        db.flush()

        db.add_all(
            [FinanceCategory(ledger_id=ledger.id, name=name, kind="expense")
             for name in DEFAULT_EXPENSE_CATEGORIES]
            + [FinanceCategory(ledger_id=ledger.id, name=name, kind="income")
               for name in DEFAULT_INCOME_CATEGORIES]
        )
        db.commit()
        db.refresh(ledger)
    except IntegrityError:
        # Например, два одновременных запроса создали книгу одному владельцу
        db.rollback()
        raise LedgerAlreadyExistsError from None
    except SQLAlchemyError:
        db.rollback()
        raise

    return ledger_to_dict(ledger, household_name, can_manage=True)


def list_categories(db: Session, access: LedgerAccess) -> list[FinanceCategory]:
    """Категории книги: сначала расходы, затем доходы, внутри по названию."""
    statement = (
        select(FinanceCategory)
        .where(FinanceCategory.ledger_id == access.ledger.id)
        .order_by(FinanceCategory.kind, FinanceCategory.name)
    )
    return list(db.scalars(statement).all())


def create_category(
    db: Session,
    access: LedgerAccess,
    data: FinanceCategoryCreate,
) -> FinanceCategory:
    """Добавляет категорию (нужны права управления)."""
    require_manage(access)

    category = FinanceCategory(ledger_id=access.ledger.id, name=data.name, kind=data.kind)

    try:
        db.add(category)
        db.commit()
        db.refresh(category)
    except IntegrityError:
        db.rollback()
        raise CategoryAlreadyExistsError from None
    except SQLAlchemyError:
        db.rollback()
        raise

    return category


def get_category(db: Session, access: LedgerAccess, category_id: int) -> FinanceCategory:
    """Находит категорию внутри книги; чужая категория считается несуществующей."""
    category = db.get(FinanceCategory, category_id)

    if category is None or category.ledger_id != access.ledger.id:
        raise CategoryNotFoundError

    return category


def delete_category(db: Session, access: LedgerAccess, category_id: int) -> None:
    """Удаляет категорию без операций вместе с её лимитом (нужны права управления)."""
    require_manage(access)
    category = get_category(db, access, category_id)

    used = db.scalar(
        select(func.count(FinanceTransaction.id)).where(
            FinanceTransaction.category_id == category.id
        )
    )
    if used:
        raise CategoryInUseError

    try:
        db.execute(delete(FinanceBudget).where(FinanceBudget.category_id == category.id))
        db.delete(category)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def list_transactions(db: Session, access: LedgerAccess, month: str) -> list[dict]:
    """Операции книги за месяц ("2026-10"): сначала новые."""
    first_day, next_month = month_bounds(month)

    statement = (
        select(FinanceTransaction, FinanceCategory.name, FinanceCategory.kind, User.name)
        .select_from(FinanceTransaction)
        .join(FinanceCategory, FinanceCategory.id == FinanceTransaction.category_id)
        .join(User, User.id == FinanceTransaction.created_by_user_id)
        .where(
            FinanceTransaction.ledger_id == access.ledger.id,
            FinanceTransaction.occurred_on >= first_day,
            FinanceTransaction.occurred_on < next_month,
        )
        .order_by(FinanceTransaction.occurred_on.desc(), FinanceTransaction.id.desc())
    )

    return [
        transaction_to_dict(transaction, category_name, kind, author_name)
        for transaction, category_name, kind, author_name in db.execute(statement).all()
    ]


def create_transaction(
    db: Session,
    access: LedgerAccess,
    user: User,
    data: FinanceTransactionCreate,
) -> dict:
    """Добавляет операцию. Доступно любому, кто имеет доступ к книге."""
    category = get_category(db, access, data.category_id)

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
        db.commit()
        db.refresh(transaction)
    except SQLAlchemyError:
        db.rollback()
        raise

    return transaction_to_dict(transaction, category.name, category.kind, user.name)


def delete_transaction(
    db: Session,
    access: LedgerAccess,
    user: User,
    transaction_id: int,
) -> None:
    """Удаляет операцию: свою может любой участник, чужую только управляющий."""
    transaction = db.get(FinanceTransaction, transaction_id)

    if transaction is None or transaction.ledger_id != access.ledger.id:
        raise TransactionNotFoundError

    if not access.can_manage and transaction.created_by_user_id != user.id:
        raise FinancePermissionError

    try:
        db.delete(transaction)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def set_budget(
    db: Session,
    access: LedgerAccess,
    category_id: int,
    monthly_limit: Decimal | None,
) -> None:
    """Задаёт, меняет или убирает (None) месячный лимит категории расходов."""
    require_manage(access)
    category = get_category(db, access, category_id)

    if category.kind != "expense":
        raise BudgetCategoryError

    budget = db.scalar(
        select(FinanceBudget).where(
            FinanceBudget.ledger_id == access.ledger.id,
            FinanceBudget.category_id == category.id,
        )
    )

    try:
        if monthly_limit is None:
            if budget is not None:
                db.delete(budget)
        elif budget is None:
            db.add(
                FinanceBudget(
                    ledger_id=access.ledger.id,
                    category_id=category.id,
                    monthly_limit=monthly_limit,
                )
            )
        else:
            budget.monthly_limit = monthly_limit

        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def get_summary(db: Session, access: LedgerAccess, month: str) -> dict:
    """Сводка за месяц: доходы, расходы, баланс и итоги по всем категориям с лимитами.

    В categories попадают все категории книги, в том числе с нулевой суммой,
    чтобы интерфейс мог показать лимиты, по которым пока нет расходов.
    """
    first_day, next_month = month_bounds(month)
    ledger_id = access.ledger.id

    # Суммы по категориям за месяц одним запросом: {id категории: сумма}
    total_rows = db.execute(
        select(FinanceTransaction.category_id, func.sum(FinanceTransaction.amount))
        .where(
            FinanceTransaction.ledger_id == ledger_id,
            FinanceTransaction.occurred_on >= first_day,
            FinanceTransaction.occurred_on < next_month,
        )
        .group_by(FinanceTransaction.category_id)
    ).all()
    totals = {category_id: total for category_id, total in total_rows}

    # Лимиты: {id категории: лимит}
    limits = {
        budget.category_id: budget.monthly_limit
        for budget in db.scalars(
            select(FinanceBudget).where(FinanceBudget.ledger_id == ledger_id)
        ).all()
    }

    income = Decimal("0")
    expense = Decimal("0")
    rows = []

    for category in list_categories(db, access):
        total = totals.get(category.id, Decimal("0"))

        if category.kind == "income":
            income += total
        else:
            expense += total

        rows.append(
            {
                "category_id": category.id,
                "name": category.name,
                "kind": category.kind,
                "total": total,
                "budget_limit": limits.get(category.id),
            }
        )

    return {
        "ledger_id": ledger_id,
        "month": month,
        "currency": access.ledger.currency,
        "income": income,
        "expense": expense,
        "balance": income - expense,
        "categories": rows,
    }