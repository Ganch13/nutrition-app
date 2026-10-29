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


class GoalNeedsExpenseError(FinancePlanError):
    """Цель указана у дохода: в цель идут только расходы (взнос, платёж по долгу или кредиту)."""

    status_code = 422
    message = "Цель можно указать только у расхода"


class GoalEntryLinkedError(FinancePlanError):
    """Запись в цели создана расходом: менять её нужно через сам расход, иначе они разойдутся."""

    status_code = 409
    message = "Запись создана расходом — измените или удалите сам расход в «Операциях»"


class SummaryOverlapError(FinancePlanError):
    """За период сводки уже есть расходы тех же категорий, а пользователь не выбрал «дополнение» или «повтор».

    Сервер сам ничего не складывает и не удаляет: интерфейс показывает окно сверки и присылает выбор (mode).
    """

    status_code = 409
    message = "За этот период уже есть расходы: выберите, это дополнение или повтор"


class SummaryReplaceError(FinancePlanError):
    """Для замены прислана операция, которой не было в окне сверки (другой период, категория или книга)."""

    status_code = 422
    message = "Заменять можно только расходы, показанные при сверке. Повторите сверку"


class SummaryNotFoundError(FinancePlanError):
    status_code = 404
    message = "Сводка не найдена"


class SummaryPermissionError(FinancePlanError):
    """Чужие расходы и чужие сводки в семейной книге удаляют только владелец и администратор семьи."""

    status_code = 403
    message = "Удалять чужие расходы могут только владелец и администратор семьи"


class BalanceUnchangedError(FinancePlanError):
    """Введённый остаток совпадает с тем, что уже насчитано: корректировать нечего."""

    status_code = 422
    message = "Баланс уже совпадает с введённой суммой"


class AdjustmentNotFoundError(FinancePlanError):
    status_code = 404
    message = "Корректировка баланса не найдена"


class AdjustmentPermissionError(FinancePlanError):
    """Чужую корректировку в семейной книге удаляют только владелец и администратор семьи."""

    status_code = 403
    message = "Удалить чужую корректировку могут только владелец и администратор семьи"
