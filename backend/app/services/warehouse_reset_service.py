"""
Полная очистка операционных данных склада. Учётные записи ADMIN сохраняются.
"""

from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    AuditLog,
    Category,
    InventoryTask,
    Order,
    OrderItem,
    Prediction,
    Product,
    Stock,
    StorageCell,
    User,
    UserRole,
)
from app.schemas.system import WarehouseResetResult
from app.services.auth_service import AuthService
from app.services.ml_service import MODELS_DIR


async def reset_warehouse_data(
    db: AsyncSession,
    actor: User,
    *,
    delete_users: bool = False,
) -> WarehouseResetResult:
    """Удаляет все данные склада. Пользователи удаляются только при delete_users=True."""
    counts: dict[str, int] = {}

    async def _count(stmt) -> int:
        r = await db.execute(stmt)
        return r.scalar() or 0

    for key, model in [
        ("predictions", Prediction),
        ("inventory_tasks", InventoryTask),
        ("order_items", OrderItem),
        ("orders", Order),
        ("stocks", Stock),
        ("products", Product),
        ("categories", Category),
        ("cells", StorageCell),
    ]:
        counts[key] = await _count(select(func.count()).select_from(model))

    counts["audit_logs"] = await _count(select(func.count()).select_from(AuditLog))
    counts["users_removed"] = 0
    if delete_users:
        counts["users_removed"] = await _count(
            select(func.count()).select_from(User).where(
                User.role != UserRole.ADMIN,
                User.id != actor.id,
            )
        )

    # Порядок удаления с учётом FK
    for model in (Prediction, InventoryTask, OrderItem, Order, Stock, Product, Category, StorageCell):
        await db.execute(delete(model))

    await db.execute(delete(AuditLog))

    if delete_users:
        admin_res = await db.execute(select(User.id).where(User.role == UserRole.ADMIN))
        admin_ids = [row[0] for row in admin_res.all()]
        if admin_ids:
            await db.execute(
                delete(User).where(
                    User.id.notin_(admin_ids),
                    User.id != actor.id,
                )
            )
            for aid in admin_ids:
                u = await db.get(User, aid)
                if u:
                    u.is_active = True
        else:
            await db.execute(delete(User).where(User.id != actor.id))

    ml_removed = 0
    if MODELS_DIR.exists():
        for path in MODELS_DIR.glob("product_*"):
            if path.is_file():
                path.unlink(missing_ok=True)
                ml_removed += 1

    db.add(AuditLog(
        user_id=actor.id,
        action="WAREHOUSE_RESET",
        entity="System",
        detail={
            "users_removed": counts["users_removed"],
            "orders_removed": counts["orders"],
            "products_removed": counts["products"],
            "cells_removed": counts["cells"],
            "ml_models_removed": ml_removed,
        },
    ))
    await db.commit()

    await AuthService.ensure_admin_exists(db)

    if delete_users:
        detail = (
            "Данные склада очищены. Удалены пользователи (кроме администраторов). "
            "Вход: admin / admin123 (если админ был пересоздан)."
        )
    else:
        detail = "Данные склада очищены. Учётные записи пользователей сохранены."

    return WarehouseResetResult(
        detail=detail,
        users_removed=counts["users_removed"],
        orders_removed=counts["orders"],
        order_items_removed=counts["order_items"],
        inventory_tasks_removed=counts["inventory_tasks"],
        stocks_removed=counts["stocks"],
        products_removed=counts["products"],
        categories_removed=counts["categories"],
        cells_removed=counts["cells"],
        predictions_removed=counts["predictions"],
        audit_logs_removed=counts["audit_logs"],
        ml_models_removed=ml_removed,
    )
