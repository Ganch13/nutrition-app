"""HTTP-эндпоинты финансов (раздел /finance)."""

from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from finance_services import (
    BudgetCategoryError,
    CategoryAlreadyExistsError,
    CategoryInUseError,
    CategoryNotFoundError,
    FinanceHouseholdNotFoundError,
    FinancePermissionError,
    LedgerAccess,
    LedgerAlreadyExistsError,
    LedgerNotFoundError,
    TransactionNotFoundError,
    create_category,
    create_ledger,
    create_transaction,
    delete_category,
    delete_transaction,
    get_ledger_access,
    get_summary,
    list_categories,
    list_ledgers,
    list_transactions,
    set_budget,
)
from finance_recurring import sync_recurring
from models import User
from schemas import (
    FinanceBudgetSet,
    FinanceCategoryCreate,
    FinanceCategoryResponse,
    FinanceSummaryResponse,
    FinanceTransactionCreate,
    FinanceTransactionResponse,
    LedgerCreate,
    LedgerResponse,
)
from security import get_current_user

router = APIRouter(prefix="/finance", tags=["finance"])

# Месяц в адресе запроса: "2026-10"
MonthQuery = Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]

# Какой ошибкой бизнес-логики какой HTTP-ответ соответствует
ERROR_RESPONSES = {
    LedgerNotFoundError: (404, "Финансовая книга не найдена"),
    FinanceHouseholdNotFoundError: (404, "Домохозяйство не найдено"),
    CategoryNotFoundError: (404, "Категория не найдена"),
    TransactionNotFoundError: (404, "Операция не найдена"),
    FinancePermissionError: (403, "Недостаточно прав для этого действия"),
    LedgerAlreadyExistsError: (409, "Финансовая книга уже создана"),
    CategoryAlreadyExistsError: (409, "Такая категория уже существует"),
    CategoryInUseError: (409, "В категории есть операции, удалить её нельзя"),
    BudgetCategoryError: (422, "Лимит можно задать только для категории расходов"),
}


def register_error_handlers(app: FastAPI) -> None:
    """Подключает к приложению преобразование ошибок финансов в HTTP-ответы.

    Благодаря этому в эндпоинтах не нужны блоки try/except: достаточно вызвать
    функцию, а ошибка сама превратится в ответ вида {"detail": "..."} с нужным кодом.
    """
    for exception_class, (status_code, detail) in ERROR_RESPONSES.items():
        # status_code и detail передаём как значения по умолчанию, чтобы каждый
        # обработчик запомнил свои значения, а не последние из цикла
        async def handler(
            request: Request,
            exc: Exception,
            status_code: int = status_code,
            detail: str = detail,
        ):
            return JSONResponse(status_code=status_code, content={"detail": detail})

        app.add_exception_handler(exception_class, handler)


def get_today(current_user: User = Depends(get_current_user)) -> date:
    """Зависимость: сегодняшняя дата по часовому поясу пользователя.

    Вынесена в зависимость, чтобы тесты могли подставить фиксированную дату
    (app.dependency_overrides[get_today] = lambda: date(2026, 10, 28)).
    """
    try:
        zone = ZoneInfo(current_user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    return datetime.now(zone).date()


def get_access(
    ledger_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LedgerAccess:
    """Зависимость: проверяет доступ текущего пользователя к книге из адреса."""
    return get_ledger_access(db, ledger_id, current_user)


@router.get("/ledgers", response_model=list[LedgerResponse])
def list_ledgers_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Книги текущего пользователя: личная и семейные."""
    return list_ledgers(db, current_user)


@router.post("/ledgers", response_model=LedgerResponse, status_code=201)
def create_ledger_endpoint(
    data: LedgerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Создаёт личную или семейную книгу (семейную: только owner и admin)."""
    return create_ledger(db, current_user, data)


@router.get("/ledgers/{ledger_id}/categories", response_model=list[FinanceCategoryResponse])
def list_categories_endpoint(
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
):
    return list_categories(db, access)


@router.post(
    "/ledgers/{ledger_id}/categories",
    response_model=FinanceCategoryResponse,
    status_code=201,
)
def create_category_endpoint(
    data: FinanceCategoryCreate,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
):
    return create_category(db, access, data)


@router.delete("/ledgers/{ledger_id}/categories/{category_id}", status_code=204)
def delete_category_endpoint(
    category_id: int,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
):
    delete_category(db, access, category_id)


@router.get(
    "/ledgers/{ledger_id}/transactions",
    response_model=list[FinanceTransactionResponse],
)
def list_transactions_endpoint(
    month: MonthQuery,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Операции за месяц: GET /finance/ledgers/1/transactions?month=2026-10"""
    # Сначала списываем платежи с автосписанием, чтобы список был актуальным
    sync_recurring(db, access.ledger.id, today)
    return list_transactions(db, access, month)


@router.post(
    "/ledgers/{ledger_id}/transactions",
    response_model=FinanceTransactionResponse,
    status_code=201,
)
def create_transaction_endpoint(
    data: FinanceTransactionCreate,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return create_transaction(db, access, current_user, data)


@router.delete("/ledgers/{ledger_id}/transactions/{transaction_id}", status_code=204)
def delete_transaction_endpoint(
    transaction_id: int,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    delete_transaction(db, access, current_user, transaction_id)


@router.put("/ledgers/{ledger_id}/budgets/{category_id}", status_code=204)
def set_budget_endpoint(
    category_id: int,
    data: FinanceBudgetSet,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
):
    """Задаёт лимит: {"monthly_limit": 200}; убирает лимит: {"monthly_limit": null}."""
    set_budget(db, access, category_id, data.monthly_limit)


@router.get("/ledgers/{ledger_id}/summary", response_model=FinanceSummaryResponse)
def summary_endpoint(
    month: MonthQuery,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Сводка за месяц: GET /finance/ledgers/1/summary?month=2026-10"""
    sync_recurring(db, access.ledger.id, today)
    return get_summary(db, access, month)