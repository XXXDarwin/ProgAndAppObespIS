from typing import Annotated, List

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AdminOnly, CurrentUser, ManagerOrAbove
from app.db.database import get_db
from app.models.models import User
from app.schemas.auth import (
    AccessTokenResponse,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserMe,
    UserOut,
)
from app.schemas.system import WarehouseResetRequest, WarehouseResetResult
from app.services.auth_service import AuthService
from app.services.warehouse_reset_service import reset_warehouse_data

router = APIRouter()


# ─── /api/auth/login ──────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse, summary="Вход в систему")
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Принимает username + password (form-data), возвращает Access и Refresh токены.
    Access-токен действует 60 минут, Refresh — 7 дней.
    """
    from app.schemas.auth import LoginRequest
    ip = request.client.host if request.client else None
    return await AuthService.login(
        LoginRequest(username=form_data.username, password=form_data.password),
        db=db,
        ip=ip,
    )


# ─── /api/auth/refresh ────────────────────────────────────────────────────────

@router.post("/refresh", response_model=AccessTokenResponse, summary="Обновить access-токен")
async def refresh_token(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await AuthService.refresh(body.refresh_token, db)


# ─── /api/auth/me ─────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserMe, summary="Текущий пользователь")
async def get_me(current_user: CurrentUser):
    return current_user


# ─── /api/auth/users — управление пользователями (только ADMIN) ───────────────

@router.get(
    "/users",
    response_model=List[UserOut],
    summary="Список пользователей",
    dependencies=[ManagerOrAbove],
)
async def list_users(db: Annotated[AsyncSession, Depends(get_db)]):
    from sqlalchemy import select
    result = await db.execute(select(User).order_by(User.created_at))
    return result.scalars().all()


@router.post(
    "/users",
    response_model=UserOut,
    status_code=201,
    summary="Создать пользователя",
    dependencies=[AdminOnly],
)
async def create_user(
    data: UserCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await AuthService.create_user(data, db, created_by=current_user)


@router.put(
    "/users/{user_id}/deactivate",
    response_model=UserOut,
    summary="Деактивировать пользователя",
    dependencies=[AdminOnly],
)
async def deactivate_user(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import AuditLog
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.is_active = False
    db.add(AuditLog(
        user_id=current_user.id,
        action="DEACTIVATE_USER",
        entity="User",
        entity_id=str(user.id),
    ))
    await db.commit()
    await db.refresh(user)
    return user


@router.delete(
    "/users/{user_id}",
    summary="Удалить (деактивировать) пользователя",
    dependencies=[AdminOnly],
)
async def delete_user(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    # Реализуем удаление как деактивацию, чтобы не ломать историю заказов/аудит.
    if str(current_user.id) == user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")
    return await deactivate_user(user_id=user_id, db=db, current_user=current_user)


@router.delete(
    "/users/{user_id}/permanent",
    summary="Удалить пользователя навсегда",
    dependencies=[AdminOnly],
)
async def purge_user(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    from uuid import UUID
    return await AuthService.purge_user(UUID(user_id), db, actor=current_user)


@router.post(
    "/system/reset-warehouse",
    response_model=WarehouseResetResult,
    summary="Полная очистка данных склада",
    dependencies=[AdminOnly],
)
async def reset_warehouse(
    payload: WarehouseResetRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Удаляет товары, ячейки, остатки, заказы, прогнозы, аудит и ML-модели.
    Пользователи удаляются только при delete_users=true (кроме ADMIN и текущего админа).
    """
    return await reset_warehouse_data(
        db, actor=current_user, delete_users=payload.delete_users
    )
