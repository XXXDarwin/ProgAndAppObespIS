from uuid import UUID

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt import create_access_token, create_refresh_token, decode_token
from app.core.security import hash_password, verify_password
from app.models.models import AuditLog, User, UserRole
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate


class AuthService:

    # ─── Login ────────────────────────────────────────────────────────────────

    @staticmethod
    async def login(data: LoginRequest, db: AsyncSession, ip: str | None = None) -> TokenResponse:
        result = await db.execute(select(User).where(User.username == data.username))
        user: User | None = result.scalar_one_or_none()

        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверное имя пользователя или пароль",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Учётная запись деактивирована",
            )

        access_token = create_access_token(str(user.id), user.role.value)
        refresh_token = create_refresh_token(str(user.id))

        # Аудит
        db.add(AuditLog(
            user_id=user.id,
            action="LOGIN",
            entity="User",
            entity_id=str(user.id),
            ip_address=ip,
        ))
        await db.commit()

        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    # ─── Refresh ──────────────────────────────────────────────────────────────

    @staticmethod
    async def refresh(refresh_token: str, db: AsyncSession):
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Невалидный refresh-токен",
            )

        user_id = payload.get("sub")
        result = await db.execute(select(User).where(User.id == UUID(user_id)))
        user: User | None = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")

        access_token = create_access_token(str(user.id), user.role.value)
        return {"access_token": access_token, "token_type": "bearer"}

    # ─── Create user ──────────────────────────────────────────────────────────

    @staticmethod
    async def create_user(data: UserCreate, db: AsyncSession, created_by: User | None = None) -> User:
        existing = await db.execute(select(User).where(User.username == data.username))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Пользователь '{data.username}' уже существует",
            )

        user = User(
            username=data.username,
            full_name=data.full_name,
            password_hash=hash_password(data.password),
            role=data.role,
        )
        db.add(user)
        await db.flush()  # получаем id до commit

        db.add(AuditLog(
            user_id=created_by.id if created_by else None,
            action="CREATE_USER",
            entity="User",
            entity_id=str(user.id),
            detail={"username": user.username, "role": user.role.value},
        ))
        await db.commit()
        await db.refresh(user)
        return user

    # ─── Permanent delete ─────────────────────────────────────────────────────

    @staticmethod
    async def purge_user(user_id: UUID, db: AsyncSession, actor: User) -> dict:
        """Физически удаляет деактивированного пользователя. Связанные записи — SET NULL."""
        if actor.id == user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя удалить самого себя",
            )

        result = await db.execute(select(User).where(User.id == user_id))
        user: User | None = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

        if user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Сначала деактивируйте пользователя",
            )

        username = user.username
        uid = str(user.id)
        db.add(AuditLog(
            user_id=actor.id,
            action="PURGE_USER",
            entity="User",
            entity_id=uid,
            detail={"username": username},
        ))
        await db.delete(user)
        await db.commit()
        return {"detail": f"Пользователь {username} удалён навсегда"}

    # ─── Seed admin ───────────────────────────────────────────────────────────

    @staticmethod
    async def ensure_admin_exists(db: AsyncSession) -> None:
        """Гарантирует хотя бы одного активного ADMIN (после сброса склада или пустой БД)."""
        result = await db.execute(
            select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True)).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            return

        by_name = await db.execute(select(User).where(User.username == "admin").limit(1))
        admin = by_name.scalar_one_or_none()
        if admin:
            admin.role = UserRole.ADMIN
            admin.is_active = True
            if not admin.full_name:
                admin.full_name = "Администратор"
            await db.commit()
            return

        admin = User(
            username="admin",
            full_name="Администратор",
            password_hash=hash_password("admin123"),
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.commit()
        print("✅ Создан пользователь по умолчанию: admin / admin123")
