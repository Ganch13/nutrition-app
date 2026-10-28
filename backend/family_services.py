"""Семейное планирование питания (шаг 69).

Идея: у каждого человека остаются свои нормы, расписание, цели и план. Семья добавляет поверх
три вещи — общий ужин (одно блюдо на двоих, порции у каждого свои), общий список закупок и
общий план готовки.

Приватность. План другого человека виден только по его согласию: каждый участник сам включает
«Планировать вместе» (HouseholdMember.plans_together). Пока флаг выключен, его данные не попадают
ни в семейный план, ни в список закупок. Вес, нормы и калории других участников в семейных
ответах не показываются — только что, когда и в каком размере порции.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from meal_plan_services import (
    MealPlanNoRecipesError,
    load_plan_user,
    run_generation,
)
from models import HouseholdMember, PlannedMeal, User
from norms_services import compute_day_target
from schemas import (
    FamilyPlanDay,
    FamilyPlanGenerateRequest,
    FamilyPlanGenerateResponse,
    FamilyPlanMemberDay,
    FamilyPlanMemberResult,
    FamilyPlannedMeal,
    FamilyPlanningMember,
    FamilyPlanningState,
    FamilyPlanWeekResponse,
)


class FamilyPlanningNotJoinedError(Exception):
    # Человек сам не включил «Планировать вместе», поэтому семейные данные ему недоступны
    pass


class FamilyPlanningNotEnoughMembersError(Exception):
    # Для общего плана нужны минимум двое подходящих участников
    pass


def _members(db: Session, household_id: int) -> list[tuple[HouseholdMember, User]]:
    """Все участники семьи в порядке вступления: [(членство, пользователь), ...]."""
    return list(
        db.execute(
            select(HouseholdMember, User)
            .join(User, User.id == HouseholdMember.user_id)
            .where(HouseholdMember.household_id == household_id)
            .order_by(HouseholdMember.joined_at, HouseholdMember.user_id)
        ).all()
    )


def _to_member(member: HouseholdMember, user: User, current_user_id: int) -> FamilyPlanningMember:
    return FamilyPlanningMember(
        user_id=user.id,
        name=user.name,
        role=member.role,
        plans_together=member.plans_together,
        is_me=user.id == current_user_id,
    )


def get_planning_state(db: Session, household_id: int, current_user_id: int) -> FamilyPlanningState:
    """Кто в семье включил «Планировать вместе».

    Пример ответа: {"household_id": 1, "together_count": 1, "members": [
        {"user_id": 1, "name": "Даня", "role": "owner", "plans_together": true, "is_me": true},
        {"user_id": 2, "name": "Леся", "role": "member", "plans_together": false, "is_me": false}]}
    """
    members = [_to_member(member, user, current_user_id) for member, user in _members(db, household_id)]
    return FamilyPlanningState(
        household_id=household_id,
        members=members,
        together_count=sum(1 for member in members if member.plans_together),
    )


def set_my_planning(db: Session, household_id: int, current_user_id: int, plans_together: bool) -> FamilyPlanningState:
    """Включает или выключает участие текущего пользователя в общем плане.

    Выключение ничего не удаляет: личный план остаётся, просто перестаёт быть виден семье.
    """
    membership = db.get(HouseholdMember, (household_id, current_user_id))
    try:
        membership.plans_together = plans_together  # type: ignore[union-attr]  # членство проверено в маршруте
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return get_planning_state(db, household_id, current_user_id)


def together_members(db: Session, household_id: int, current_user_id: int) -> dict[int, str]:
    """Участники, планирующие вместе: {id: имя} в порядке вступления.

    Пример: {1: "Даня", 2: "Леся"}. Сам запрашивающий тоже должен был включить «Планировать
    вместе», иначе FamilyPlanningNotJoinedError: нельзя смотреть чужое, не открыв своё.
    """
    result = {user.id: user.name for member, user in _members(db, household_id) if member.plans_together}
    if current_user_id not in result:
        raise FamilyPlanningNotJoinedError
    return result


def get_family_week(db: Session, household_id: int, current_user_id: int, start: date) -> FamilyPlanWeekResponse:
    """Планы всех участников на 7 дней, начиная со start (без калорий и БЖУ)."""
    names = together_members(db, household_id, current_user_id)
    days = [start + timedelta(days=offset) for offset in range(7)]
    meals = db.scalars(
        select(PlannedMeal)
        .where(PlannedMeal.user_id.in_(list(names)), PlannedMeal.plan_date >= days[0], PlannedMeal.plan_date <= days[-1])
        .order_by(PlannedMeal.planned_at, PlannedMeal.id)
    ).all()

    # Блюдо «общее», если в один день на один приём пищи его запланировали минимум двое
    eaters: dict[tuple, set[int]] = {}
    for meal in meals:
        if meal.recipe_id is not None:
            eaters.setdefault((meal.plan_date, meal.meal_type, meal.recipe_id), set()).add(meal.user_id)

    result_days = []
    for day in days:
        result_days.append(
            FamilyPlanDay(
                date=day,
                members=[
                    FamilyPlanMemberDay(
                        user_id=user_id,
                        name=name,
                        meals=[
                            FamilyPlannedMeal(
                                id=meal.id,
                                planned_at=meal.planned_at,
                                meal_type=meal.meal_type,  # type: ignore[arg-type]
                                location=meal.location,  # type: ignore[arg-type]
                                status=meal.status,  # type: ignore[arg-type]
                                title=meal.title,
                                recipe_id=meal.recipe_id,
                                portion_scale=meal.portion_scale,
                                shared=meal.recipe_id is not None
                                and len(eaters[(meal.plan_date, meal.meal_type, meal.recipe_id)]) >= 2,
                            )
                            for meal in meals
                            if meal.user_id == user_id and meal.plan_date == day
                        ],
                    )
                    for user_id, name in names.items()
                ],
            )
        )

    return FamilyPlanWeekResponse(
        household_id=household_id,
        start=days[0],
        end=days[-1],
        members=[
            _to_member(member, user, current_user_id)
            for member, user in _members(db, household_id)
            if member.plans_together
        ],
        days=result_days,
    )


def generate_family_plan(
    db: Session, household_id: int, current_user_id: int, data: FamilyPlanGenerateRequest
) -> FamilyPlanGenerateResponse:
    """Составляет планы всем участникам, включившим «Планировать вместе», и общий ужин для них.

    Что происходит:
      1. берём тех, кто включил «Планировать вместе» и у кого посчитаны нормы (вес, дата рождения);
         остальным пишем предупреждение и план не составляем;
      2. для общих приёмов пищи (по умолчанию ужин) ищем рецепты, доступные каждому участнику;
      3. дальше всё как в личном плане, только общий ужин: одно блюдо, время по самому позднему
         из участников, порция у каждого своя — под его норму калорий.

    overwrite=true заменяет ещё не съеденное у всех участников — согласие дано включением флага.
    """
    names = together_members(db, household_id, current_user_id)
    days = [data.start + timedelta(days=offset) for offset in range(data.days)]

    warnings: list[str] = []
    users = []
    for user_id, name in names.items():
        if not compute_day_target(db, user_id, days[0]).ready:
            warnings.append(f"{name}: нужны вес и дата рождения — план для этого участника не составлен.")
            continue
        users.append(load_plan_user(db, user_id, name, days))

    if len(users) < 2:
        raise FamilyPlanningNotEnoughMembersError
    if not any(user.options for user in users):
        raise MealPlanNoRecipesError

    # Общие рецепты — те, что видны каждому: пересечение по id
    common_ids = set.intersection(*[{option.recipe.id for option in user.options} for user in users])
    shared_options = [option for option in users[0].options if option.recipe.id in common_ids]
    if data.shared_meal_types and not shared_options:
        warnings.append("Нет рецептов, доступных всем участникам: общие приёмы пищи составлены не будут.")

    run_warnings, shared_meals = run_generation(
        db,
        users,
        days,
        overwrite=data.overwrite,
        batch_days=data.batch_days,
        shared_types=tuple(data.shared_meal_types),
        shared_options=shared_options,
    )
    return FamilyPlanGenerateResponse(
        members=[
            FamilyPlanMemberResult(
                user_id=user.user_id,
                name=user.label,
                created_meals=user.created,
                replaced_meals=user.replaced,
                skipped_days=user.skipped_days,
            )
            for user in users
        ],
        shared_meals=shared_meals,
        warnings=warnings + run_warnings,
    )
