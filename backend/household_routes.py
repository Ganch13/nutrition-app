"""Эндпоинты приглашений и управления участниками домохозяйства (шаг 62)."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from access import require_household_member
from database import get_db
from household_services import (
    InsufficientRoleError,
    InvalidInviteError,
    InviteNotFoundError,
    MemberNotFoundError,
    OwnerProtectedError,
    change_member_role,
    create_invite,
    join_household,
    list_active_invites,
    remove_member,
    revoke_invite,
)
from models import User
from schemas import (
    HouseholdInviteResponse,
    HouseholdJoinRequest,
    HouseholdMemberDetailResponse,
    HouseholdMemberRoleUpdate,
    UserHouseholdResponse,
)
from security import get_current_user
from services import HouseholdMemberAlreadyExistsError

router = APIRouter(tags=["household-management"])


@router.post(
    "/households/{household_id}/invites",
    response_model=HouseholdInviteResponse,
    status_code=201,
)
def create_invite_endpoint(
    household_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Создаёт код приглашения. Могут владелец и администратор.

    Запрос: POST /households/1/invites (тела нет), заголовок Authorization: Bearer ...
    Ответ 201: {"id": 1, "household_id": 1, "code": "K7M29QXP", "created_at": "...", "expires_at": "..."}
    """
    require_household_member(
        household_id=household_id,
        db=db,
        current_user=current_user,
        allowed_roles=("owner", "admin"),
    )
    return create_invite(db=db, household_id=household_id, created_by_user_id=current_user.id)


@router.get(
    "/households/{household_id}/invites",
    response_model=list[HouseholdInviteResponse],
)
def list_invites_endpoint(
    household_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Действующие (неиспользованные, непросроченные) коды. Владелец и администратор."""
    require_household_member(
        household_id=household_id,
        db=db,
        current_user=current_user,
        allowed_roles=("owner", "admin"),
    )
    return list_active_invites(db=db, household_id=household_id)


@router.delete("/households/{household_id}/invites/{invite_id}", status_code=204)
def revoke_invite_endpoint(
    household_id: int,
    invite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отзывает неиспользованный код. Владелец и администратор. Ответ 204 без тела."""
    require_household_member(
        household_id=household_id,
        db=db,
        current_user=current_user,
        allowed_roles=("owner", "admin"),
    )
    try:
        revoke_invite(db=db, household_id=household_id, invite_id=invite_id)
    except InviteNotFoundError:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")
    return Response(status_code=204)


@router.post("/households/join", response_model=UserHouseholdResponse)
def join_household_endpoint(
    data: HouseholdJoinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Вступление в домохозяйство по коду.

    Запрос: POST /households/join, тело {"code": "K7M2-9QXP"}
    Ответ 200: {"id": 1, "name": "Дом", "created_at": "...", "role": "member"}
    Ошибки: 404 — код недействителен, просрочен или использован (одно сообщение
    на все случаи); 409 — вы уже в этом домохозяйстве.
    """
    try:
        return join_household(db=db, user_id=current_user.id, raw_code=data.code)
    except InvalidInviteError:
        raise HTTPException(
            status_code=404,
            detail="Код приглашения недействителен, истёк или уже использован",
        )
    except HouseholdMemberAlreadyExistsError:
        raise HTTPException(status_code=409, detail="Вы уже состоите в этом домохозяйстве")


@router.patch(
    "/households/{household_id}/members/{user_id}",
    response_model=HouseholdMemberDetailResponse,
)
def change_member_role_endpoint(
    household_id: int,
    user_id: int,
    data: HouseholdMemberRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Меняет роль участника (admin ⇄ member). Только владелец.

    Запрос: PATCH /households/1/members/2, тело {"role": "admin"}
    """
    require_household_member(
        household_id=household_id,
        db=db,
        current_user=current_user,
        allowed_roles=("owner",),
    )
    try:
        return change_member_role(
            db=db,
            household_id=household_id,
            target_user_id=user_id,
            new_role=data.role,
        )
    except MemberNotFoundError:
        raise HTTPException(status_code=404, detail="Участник не найден")
    except OwnerProtectedError:
        raise HTTPException(status_code=409, detail="Роль владельца изменить нельзя")


@router.delete("/households/{household_id}/members/{user_id}", status_code=204)
def remove_member_endpoint(
    household_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Удаляет участника или позволяет выйти самому (user_id = ваш id).

    Запрос: DELETE /households/1/members/2. Правила описаны в remove_member.
    """
    # Здесь достаточно быть участником; тонкие правила проверяет сервис
    acting = require_household_member(
        household_id=household_id,
        db=db,
        current_user=current_user,
    )
    try:
        remove_member(db=db, household_id=household_id, target_user_id=user_id, acting=acting)
    except MemberNotFoundError:
        raise HTTPException(status_code=404, detail="Участник не найден")
    except InsufficientRoleError:
        raise HTTPException(status_code=403, detail="Недостаточно прав для выполнения действия")
    except OwnerProtectedError:
        raise HTTPException(
            status_code=409,
            detail="Владелец не может покинуть домохозяйство или быть удалён",
        )
    return Response(status_code=204)