"""Ошибки новых финансовых разделов: повторяющиеся операции, циклы, цели.

Каждая ошибка знает свой HTTP-код (status_code) и текст для пользователя (message). Один общий
обработчик (register_finance_plan_errors в finance_plan_routes.py) превращает любую из них в ответ
{"detail": "текст"}, поэтому в эндпоинтах не нужны блоки try/except.
Текст можно задать при создании ошибки, если в нём нужны числа:
    raise PaymentTooLargeError("Платёж больше остатка с процентами: не более 105 000 ₽")
"""


class FinancePlanError(Exception):
    """Базовая ошибка: код ответа и сообщение по умолчанию переопределяются в наследниках."""

    status_code = 422
    message = "Некорректный запрос"

    def __init__(self, message: str | None = None):
        self.message = message or self.message
        super().__init__(self.message)


class RuleNotFoundError(FinancePlanError):
    status_code = 404
    message = "Повторяющаяся операция не найдена"


class OccurrenceNotDueError(FinancePlanError):
    """В указанную дату по правилу нет платежа (например, 11 число у правила «10 числа каждого месяца»)."""

    status_code = 422
    message = "По этому правилу в указанную дату платежа нет"


class OccurrenceAlreadyHandledError(FinancePlanError):
    status_code = 409
    message = "Эта выплата уже отмечена"


class OccurrenceNotHandledError(FinancePlanError):
    status_code = 404
    message = "Эта выплата ещё не отмечена"


class RuleCategoryError(FinancePlanError):
    """Категория не подходит: другого типа (доход/расход) или её нет в этой книге."""

    status_code = 422
    message = "Категория не подходит к этой операции"


class GoalNotFoundError(FinancePlanError):
    status_code = 404
    message = "Цель не найдена"


class GoalEntryNotFoundError(FinancePlanError):
    status_code = 404
    message = "Запись в цели не найдена"


class GoalPermissionError(FinancePlanError):
    status_code = 403
    message = "Недостаточно прав для этого действия"


class GoalSharedNeedsFamilyError(FinancePlanError):
    status_code = 409
    message = "Для совместной цели нужна семья с общей книгой"


class PaymentTooLargeError(FinancePlanError):
    status_code = 422
    message = "Платёж больше остатка долга"


class GoalClosedError(FinancePlanError):
    status_code = 409
    message = "Цель уже достигнута, новые взносы не нужны"
