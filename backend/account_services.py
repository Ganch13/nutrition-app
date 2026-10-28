"""Удаление аккаунта (раздел «Профиль» → «Удалить аккаунт»).

Зачем отдельный модуль: у пользователя десятки связанных таблиц (питание, тренировки, расписание, фото,
финансы, семьи). Удалить только строку в users нельзя: база не позволит, пока на неё ссылаются другие строки.
Здесь собран весь порядок удаления и правила для общих (семейных) данных.

Правила для семей, где состоит пользователь:
  * он единственный участник: семья удаляется целиком вместе с общими продуктами, рецептами и финансами;
  * участники есть, он владелец: владение переходит к самому давнему администратору, а если их нет,
    к самому давнему участнику; семья и её данные остаются;
  * участники есть, он не владелец: он просто выходит из семьи.
Общие продукты и рецепты, которые он создал, остаются семье; операции в семейной книге остаются
и подписываются «Удалённый пользователь».
"""

import logging
from pathlib import Path

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finance_services import delete_ledger_data
from models import (
    FinanceTransaction,
    Food,
    Goal,
    Household,
    HouseholdInvite,
    HouseholdMember,
    Ledger,
    MealEntry,
    NutritionSettings,
    PlannedMeal,
    ProgressPhoto,
    Recipe,
    ScheduleEvent,
    ShoppingCheck,
    TrainingSession,
    User,
    WeightRecord,
    Workout,
)
from auth_services import WrongPasswordError
from photo_services import photo_path
from security import verify_password

logger = logging.getLogger(__name__)

# Порядок выбора нового владельца семьи: сначала администраторы, затем участники
_ROLE_ORDER = {"admin": 0, "member": 1}


def _other_members(db: Session, household_id: int, user_id: int) -> list[HouseholdMember]:
    """Остальные участники семьи, самые подходящие в наследники владения первыми.

    Пример: [HouseholdMember(user_id=2, role="admin"), HouseholdMember(user_id=3, role="member")].
    """
    members = db.scalars(
        select(HouseholdMember).where(
            HouseholdMember.household_id == household_id,
            HouseholdMember.user_id != user_id,
        )
    ).all()
    return sorted(members, key=lambda m: (_ROLE_ORDER.get(m.role, 2), m.joined_at, m.user_id))


def preview_account_deletion(db: Session, user: User) -> dict:
    """Показывает, что произойдёт при удалении аккаунта (ничего не меняет).

    Пример ответа:
        {"email": "danya@example.com",
         "households_to_delete": [{"id": 2, "name": "Одиночка"}],
         "households_to_leave": [{"id": 1, "name": "Семья", "new_owner_name": "Леся"}],
         "counts": {"weight_records": 12, "meal_entries": 340, "training_sessions": 20,
                    "progress_photos": 4, "finance_transactions": 87}}
    new_owner_name заполнено, только если пользователь владелец и владение перейдёт к другому.
    """
    to_delete: list[dict] = []
    to_leave: list[dict] = []

    memberships = db.scalars(select(HouseholdMember).where(HouseholdMember.user_id == user.id)).all()
    for membership in memberships:
        household = db.get(Household, membership.household_id)
        others = _other_members(db, membership.household_id, user.id)
        if not others:
            to_delete.append({"id": household.id, "name": household.name})
            continue
        new_owner_name = None
        if membership.role == "owner":
            new_owner_name = db.get(User, others[0].user_id).name
        to_leave.append({"id": household.id, "name": household.name, "new_owner_name": new_owner_name})

    def count(model, *conditions) -> int:
        return db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0


    personal_ledger_ids = select(Ledger.id).where(Ledger.user_id == user.id)
    deleted_household_ids = [item["id"] for item in to_delete]
    ledger_ids = personal_ledger_ids
    if deleted_household_ids:
        ledger_ids = select(Ledger.id).where(
            (Ledger.user_id == user.id) | (Ledger.household_id.in_(deleted_household_ids))
        )

    return {
        "email": user.email,
        "households_to_delete": to_delete,
        "households_to_leave": to_leave,
        "counts": {
            "weight_records": count(WeightRecord, WeightRecord.user_id == user.id),
            "meal_entries": count(MealEntry, MealEntry.user_id == user.id),
            "training_sessions": count(TrainingSession, TrainingSession.user_id == user.id),
            "progress_photos": count(ProgressPhoto, ProgressPhoto.user_id == user.id),
            "finance_transactions": count(
                FinanceTransaction, FinanceTransaction.ledger_id.in_(ledger_ids)
            ),
        },
    }


def _delete_household(db: Session, household_id: int) -> None:
    """Удаляет семью целиком: книгу, общие рецепты и продукты, приглашения, участников."""
    ledger = db.scalar(select(Ledger).where(Ledger.household_id == household_id))
    if ledger is not None:
        delete_ledger_data(db, ledger.id)

    # Сначала рецепты (их ингредиенты удаляются каскадом), затем продукты, на которые они ссылались
    db.execute(delete(Recipe).where(Recipe.household_id == household_id))
    db.execute(delete(Food).where(Food.household_id == household_id))
    db.execute(delete(HouseholdInvite).where(HouseholdInvite.household_id == household_id))
    db.execute(delete(HouseholdMember).where(HouseholdMember.household_id == household_id))
    db.execute(delete(Household).where(Household.id == household_id))


def delete_account(db: Session, user: User, password: str) -> list[Path]:
    """Удаляет пользователя и все его данные одной транзакцией; возвращает пути файлов фото.

    Пароль проверяется заново: украденный токен доступа сам по себе не должен стирать аккаунт.
    Файлы фото удаляет вызывающий код ПОСЛЕ успешного коммита (см. remove_files):
    если бы файлы стёрлись раньше, а база откатилась, фото потерялись бы навсегда.
    Ошибка: WrongPasswordError.
    """
    if user.password_hash is None or not verify_password(password, user.password_hash):
        raise WrongPasswordError

    user_id = user.id
    photos = db.scalars(select(ProgressPhoto).where(ProgressPhoto.user_id == user_id)).all()
    photo_files = [photo_path(photo) for photo in photos]

    try:
        # 1. Личные рецепты и продукты: сначала рецепты, ингредиенты которых ссылаются на продукты
        db.execute(delete(Recipe).where(Recipe.owner_user_id == user_id, Recipe.household_id.is_(None)))
        db.execute(delete(Food).where(Food.owner_user_id == user_id, Food.household_id.is_(None)))

        # 2. Семьи: удалить, передать владение или просто выйти
        memberships = db.scalars(select(HouseholdMember).where(HouseholdMember.user_id == user_id)).all()
        for membership in memberships:
            household_id = membership.household_id
            others = _other_members(db, household_id, user_id)
            if not others:
                _delete_household(db, household_id)
                continue
            if membership.role == "owner":
                others[0].role = "owner"
            # Общие продукты и рецепты остаются семье без личного автора
            db.execute(
                update(Food).where(Food.household_id == household_id, Food.owner_user_id == user_id).values(owner_user_id=None)
            )
            db.execute(
                update(Recipe)
                .where(Recipe.household_id == household_id, Recipe.owner_user_id == user_id)
                .values(owner_user_id=None)
            )
            db.delete(membership)
        db.flush()

        # 3. Приглашения: созданные им коды отзываются, на использованных остаётся пустое «кто вступил»
        db.execute(delete(HouseholdInvite).where(HouseholdInvite.created_by_user_id == user_id))
        db.execute(
            update(HouseholdInvite).where(HouseholdInvite.used_by_user_id == user_id).values(used_by_user_id=None)
        )

        # 4. Личная финансовая книга со всем содержимым
        for ledger_id in db.scalars(select(Ledger.id).where(Ledger.user_id == user_id)).all():
            delete_ledger_data(db, ledger_id)

        # 5. Тренировки: отдельные тренировки → сессии → события расписания, на которые сессии ссылались
        session_ids = select(TrainingSession.id).where(TrainingSession.user_id == user_id)
        db.execute(delete(Workout).where(Workout.training_session_id.in_(session_ids)))
        db.execute(delete(TrainingSession).where(TrainingSession.user_id == user_id))
        db.execute(delete(ScheduleEvent).where(ScheduleEvent.user_id == user_id))

        # 6. Питание: пункты плана удаляются каскадом, затем записи приёмов пищи
        db.execute(delete(PlannedMeal).where(PlannedMeal.user_id == user_id))
        db.execute(delete(MealEntry).where(MealEntry.user_id == user_id))

        # 7. Остальное личное
        db.execute(delete(WeightRecord).where(WeightRecord.user_id == user_id))
        db.execute(delete(Goal).where(Goal.user_id == user_id))
        db.execute(delete(NutritionSettings).where(NutritionSettings.user_id == user_id))
        db.execute(delete(ProgressPhoto).where(ProgressPhoto.user_id == user_id))
        db.execute(delete(ShoppingCheck).where(ShoppingCheck.checked_by_user_id == user_id))

        # 8. Сам пользователь. Сессии (refresh_tokens) база удаляет каскадом,
        # а подписи авторов операций и целей в общих книгах очищает через SET NULL
        db.execute(delete(User).where(User.id == user_id))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    return photo_files


def remove_files(paths: list[Path]) -> None:
    """Удаляет файлы фото и пустую папку пользователя. Ошибки только пишутся в журнал.

    Файл, который не получилось стереть, остаётся «сиротой» на диске, но данных в базе уже нет,
    поэтому пользователю это не мешает; администратор увидит предупреждение в журнале.
    """
    folders: set[Path] = set()
    for path in paths:
        folders.add(path.parent)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Не удалось удалить файл фото %s", path, exc_info=True)
    for folder in folders:
        try:
            folder.rmdir()  # удалится, только если папка пуста
        except OSError:
            pass
