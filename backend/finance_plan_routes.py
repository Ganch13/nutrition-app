"""HTTP-эндпоинты планирования финансов (релиз 1.1).

Что здесь:
  * повторяющиеся доходы и обязательные платежи: /finance/ledgers/{id}/recurring;
  * вопрос «Поступил ли платёж?» по всем книгам: /finance/income-prompts;
  * деньги для главной страницы (всего и свободно в периоде): /finance/home;
  * баланс книги и корректировки «на счетах на самом деле столько-то»: /finance/ledgers/{id}/balance;
  * ближайшие выплаты и бюджетные циклы: /upcoming, /cycles, /period-summary, переключатель режима;
  * оценка долговой нагрузки: /load и /load/simulate;
  * финансовые цели (накопления, долги, кредиты): /goals.
Права доступа проверяет зависимость get_access из finance_routes: к чужой книге доступа нет.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from finance_balance import delete_adjustment, get_balance, set_actual_balance
from finance_errors import FinancePlanError
from finance_goals import (
    add_entry,
    create_goal,
    delete_entry,
    delete_goal,
    get_goal_detail,
    list_goals,
    update_goal,
)
from finance_planning import (
    get_cycles,
    get_load,
    home_overview,
    period_summary,
    set_cycle_mode,
    simulate_payment,
)
from finance_recurring import (
    confirm_occurrence,
    create_rule,
    delete_rule,
    get_rule_dict,
    income_prompts,
    list_rules,
    skip_occurrence,
    sync_recurring,
    undo_occurrence,
    update_rule,
    upcoming,
)
from finance_routes import get_access, get_today
from finance_services import LedgerAccess, list_ledgers, require_manage
from models import User
from schemas import (
    BalanceSet,
    CyclesResponse,
    LedgerBalanceResponse,
    FinanceTransactionResponse,
    FinanceGoalCreate,
    FinanceGoalDetailResponse,
    FinanceGoalEntryCreate,
    FinanceGoalResponse,
    FinanceGoalUpdate,
    FinanceHomeLedger,
    IncomePromptResponse,
    LedgerCycleUpdate,
    LedgerResponse,
    LoadResponse,
    LoadSimulationResponse,
    OccurrenceConfirm,
    OccurrenceResponse,
    PeriodSummaryResponse,
    RecurringRuleCreate,
    RecurringRuleResponse,
    RecurringRuleUpdate,
)
from security import get_current_user

router = APIRouter(prefix="/finance", tags=["finance-plan"])


def register_finance_plan_errors(app: FastAPI) -> None:
    """Превращает любую FinancePlanError в ответ {"detail": "..."} с её кодом (404, 409, 422 и т. д.)."""

    async def handler(request: Request, exc: Exception):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})  # type: ignore[attr-defined]

    app.add_exception_handler(FinancePlanError, handler)


# ---------------------------------------------------------------------------
# Сводки по всем книгам пользователя
# ---------------------------------------------------------------------------


@router.get("/income-prompts", response_model=list[IncomePromptResponse])
def income_prompts_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    """Поступления, о которых пора спросить «Поступил ли платёж?» (±2 дня от плановой даты).

    Ответ «да» — POST .../recurring/{rule_id}/occurrences/{due_on}/confirm с фактической датой и суммой,
    «пропустить» — .../skip. «Нет» и «напомнить позже» на сервер не отправляются.
    """
    return income_prompts(db, current_user, today)


@router.get("/home", response_model=list[FinanceHomeLedger])
def home_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    """Деньги для главной: по каждой книге (личной и семейной) сколько всего и сколько свободно в периоде."""
    return home_overview(db, current_user, today)


# ---------------------------------------------------------------------------
# Баланс книги и корректировки («на счетах на самом деле столько-то»)
# ---------------------------------------------------------------------------


@router.get("/ledgers/{ledger_id}/balance", response_model=LedgerBalanceResponse)
def balance_endpoint(
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Баланс книги («Всего»: только фактические операции и корректировки) и последние корректировки."""
    sync_recurring(db, access.ledger.id, today)
    return get_balance(db, access, today)


@router.post("/ledgers/{ledger_id}/balance", response_model=LedgerBalanceResponse, status_code=201)
def set_balance_endpoint(
    data: BalanceSet,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    """Фактический остаток без дохода и расхода: сервер сохраняет разницу как корректировку.

    Пример: POST /finance/ledgers/1/balance с телом {"actual": 52300, "note": "сверка с банком"}.
    Если «Всего» было 50 000, сохраняется +2 300, и в ответе total = 52 300. Совпадает — 422.
    """
    # Сначала досписываем автосписания: разница считается от актуального баланса
    sync_recurring(db, access.ledger.id, today)
    return set_actual_balance(db, access, current_user, data, today)


@router.delete("/ledgers/{ledger_id}/balance/adjustments/{adjustment_id}", response_model=LedgerBalanceResponse)
def delete_adjustment_endpoint(
    adjustment_id: int,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    """Отменяет корректировку: «Всего» возвращается к прежней цифре. Ответ — обновлённый баланс."""
    return delete_adjustment(db, access, current_user, adjustment_id, today)


# ---------------------------------------------------------------------------
# Повторяющиеся доходы и обязательные платежи
# ---------------------------------------------------------------------------


@router.get("/ledgers/{ledger_id}/recurring", response_model=list[RecurringRuleResponse])
def list_rules_endpoint(
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    """Правила книги: сначала доходы, затем платежи. Попутно списываются платежи с автосписанием."""
    sync_recurring(db, access.ledger.id, today)
    return list_rules(db, access, current_user, today)


@router.post("/ledgers/{ledger_id}/recurring", response_model=RecurringRuleResponse, status_code=201)
def create_rule_endpoint(
    data: RecurringRuleCreate,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    """Создаёт повторяющийся доход или платёж.

    Пример: POST /finance/ledgers/1/recurring
    {"kind": "income", "name": "Аванс", "amount": 50000, "frequency": "monthly", "start_on": "2026-10-10"}
    """
    rule = create_rule(db, access, current_user, data, today)
    # Если платёж с автосписанием начался в прошлом, операции за прошедшие даты появляются сразу
    sync_recurring(db, access.ledger.id, today)
    return get_rule_dict(db, access, current_user, rule["id"], today)


@router.patch("/ledgers/{ledger_id}/recurring/{rule_id}", response_model=RecurringRuleResponse)
def update_rule_endpoint(
    rule_id: int,
    data: RecurringRuleUpdate,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    """Меняет правило: {"amount": 36000} или {"is_active": false} (пауза)."""
    update_rule(db, access, current_user, rule_id, data, today)
    sync_recurring(db, access.ledger.id, today)
    return get_rule_dict(db, access, current_user, rule_id, today)


@router.delete("/ledgers/{ledger_id}/recurring/{rule_id}", status_code=204)
def delete_rule_endpoint(
    rule_id: int,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Удаляет правило. Уже созданные им операции остаются в журнале."""
    delete_rule(db, access, current_user, rule_id)


@router.post(
    "/ledgers/{ledger_id}/recurring/{rule_id}/occurrences/{due_on}/confirm",
    response_model=FinanceTransactionResponse,
    status_code=201,
)
def confirm_occurrence_endpoint(
    rule_id: int,
    due_on: date,
    data: OccurrenceConfirm | None = None,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    """«Оплачено» / «Получено»: создаёт операцию за выплату.

    Пример: POST /finance/ledgers/1/recurring/3/occurrences/2026-11-03/confirm
    с телом {"amount": 34800} или без тела (тогда берётся плановая сумма).
    """
    return confirm_occurrence(db, access, current_user, rule_id, due_on, data or OccurrenceConfirm(), today)


@router.post("/ledgers/{ledger_id}/recurring/{rule_id}/occurrences/{due_on}/skip", status_code=204)
def skip_occurrence_endpoint(
    rule_id: int,
    due_on: date,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
):
    """«Пропустить»: выплата за эту дату не состоится и больше не считается ожидаемой."""
    skip_occurrence(db, access, rule_id, due_on)


@router.delete("/ledgers/{ledger_id}/recurring/{rule_id}/occurrences/{due_on}", status_code=204)
def undo_occurrence_endpoint(
    rule_id: int,
    due_on: date,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """«Отменить отметку»: выплата снова ожидается, созданная ею операция удаляется."""
    undo_occurrence(db, access, current_user, rule_id, due_on)


@router.get("/ledgers/{ledger_id}/upcoming", response_model=list[OccurrenceResponse])
def upcoming_endpoint(
    days: Annotated[int, Query(ge=1, le=120)] = 30,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Просроченные (до 60 дней назад) и ожидаемые выплаты на ближайшие `days` дней: GET .../upcoming?days=30."""
    sync_recurring(db, access.ledger.id, today)
    return upcoming(db, access, today, days)


# ---------------------------------------------------------------------------
# Бюджетные циклы
# ---------------------------------------------------------------------------


@router.patch("/ledgers/{ledger_id}", response_model=LedgerResponse)
def update_ledger_endpoint(
    data: LedgerCycleUpdate,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Переключает бюджетный период: {"cycle_mode": "income"} (от дохода до дохода) или "calendar" (месяц)."""
    require_manage(access)
    set_cycle_mode(db, access, data.cycle_mode)
    return next(item for item in list_ledgers(db, current_user) if item["id"] == access.ledger.id)


@router.get("/ledgers/{ledger_id}/cycles", response_model=CyclesResponse)
def cycles_endpoint(
    previous: Annotated[int, Query(ge=0, le=12)] = 0,
    count: Annotated[int, Query(ge=1, le=12)] = 2,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Текущий бюджетный период, следующие за ним и (по желанию) предыдущие, плюс советы.

    Пример: GET /finance/ledgers/1/cycles → текущий и следующий период (так их показывает «Обзор»).
    Советы считаются только по периодам из ответа: что не показано, в советы не попадает.
    """
    sync_recurring(db, access.ledger.id, today)
    return get_cycles(db, access, today, previous, count)


@router.get("/ledgers/{ledger_id}/period-summary", response_model=PeriodSummaryResponse)
def period_summary_endpoint(
    on: date | None = None,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Итоги бюджетного периода, в который попадает дата `on` (по умолчанию сегодня)."""
    sync_recurring(db, access.ledger.id, today)
    return period_summary(db, access, on or today)


# ---------------------------------------------------------------------------
# Долговая нагрузка
# ---------------------------------------------------------------------------


@router.get("/ledgers/{ledger_id}/load", response_model=LoadResponse)
def load_endpoint(
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Оценка нагрузки: доход, обязательные платежи, доля, статус и советы."""
    return get_load(db, access, today)


@router.get("/ledgers/{ledger_id}/load/simulate", response_model=LoadSimulationResponse)
def simulate_endpoint(
    payment: Annotated[Decimal, Query(gt=0, max_digits=12, decimal_places=2)],
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Можно ли взять ещё один ежемесячный платёж: GET .../load/simulate?payment=15000."""
    return simulate_payment(db, access, today, payment)


# ---------------------------------------------------------------------------
# Финансовые цели
# ---------------------------------------------------------------------------


@router.get("/ledgers/{ledger_id}/goals", response_model=list[FinanceGoalResponse])
def list_goals_endpoint(
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    """Цели книги: личные в личной книге, совместные в семейной."""
    return list_goals(db, access, current_user, today)


@router.post("/ledgers/{ledger_id}/goals", response_model=FinanceGoalResponse, status_code=201)
def create_goal_endpoint(
    data: FinanceGoalCreate,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    """Создаёт цель.

    Накопление: {"kind": "savings", "name": "Отпуск", "target_amount": 200000, "start_amount": 15000}
    Кредит: {"kind": "loan", "name": "Кредит", "target_amount": 100000, "interest_rate": 60, "payment_day": 15}
    """
    return create_goal(db, access, current_user, data, today)


@router.get("/ledgers/{ledger_id}/goals/{goal_id}", response_model=FinanceGoalDetailResponse)
def get_goal_endpoint(
    goal_id: int,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    """Цель с историей взносов."""
    return get_goal_detail(db, access, current_user, goal_id, today)


@router.patch("/ledgers/{ledger_id}/goals/{goal_id}", response_model=FinanceGoalResponse)
def update_goal_endpoint(
    goal_id: int,
    data: FinanceGoalUpdate,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    return update_goal(db, access, current_user, goal_id, data, today)


@router.delete("/ledgers/{ledger_id}/goals/{goal_id}", status_code=204)
def delete_goal_endpoint(
    goal_id: int,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    delete_goal(db, access, current_user, goal_id)


@router.post("/ledgers/{ledger_id}/goals/{goal_id}/entries", response_model=FinanceGoalDetailResponse, status_code=201)
def add_entry_endpoint(
    goal_id: int,
    data: FinanceGoalEntryCreate,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    """Взнос или платёж. Для кредита ответ содержит разбивку: сколько ушло на проценты и в тело долга.

    Пример: POST .../goals/5/entries {"amount": 20000, "paid_on": "2026-10-15"}
    """
    return add_entry(db, access, current_user, goal_id, data, today)


@router.delete("/ledgers/{ledger_id}/goals/{goal_id}/entries/{entry_id}", response_model=FinanceGoalDetailResponse)
def delete_entry_endpoint(
    goal_id: int,
    entry_id: int,
    access: LedgerAccess = Depends(get_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    today: date = Depends(get_today),
):
    """Удаляет взнос и пересчитывает остаток; возвращает обновлённую цель."""
    return delete_entry(db, access, current_user, goal_id, entry_id, today)
