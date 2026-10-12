from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditLog, Order, OrderItem, OrderStatus, OrderType, Product, User
from app.schemas.ml import DemandHistoryImport, DemandHistoryImportResult


async def import_demand_history(
    payload: DemandHistoryImport,
    db: AsyncSession,
    actor: User,
) -> DemandHistoryImportResult:
    """
    Создаёт завершённые заказы расхода по дневным записям спроса.
    Остатки на складе не меняются — данные нужны для обучения прогноза.
    """
    if not payload.records:
        raise HTTPException(status_code=400, detail="Список records пуст")

    skus = {r.sku.upper() for r in payload.records}
    res = await db.execute(
        select(Product).where(func.upper(Product.sku).in_(skus))
    )
    products_by_sku = {p.sku.upper(): p for p in res.scalars().all()}

    by_date: dict[str, list] = defaultdict(list)
    for rec in payload.records:
        sku_key = rec.sku.upper()
        product = products_by_sku.get(sku_key)
        if not product:
            raise HTTPException(
                status_code=400,
                detail=f"Товар с SKU «{rec.sku}» не найден. Сначала импортируйте каталог.",
            )
        day = rec.date.isoformat() if hasattr(rec.date, "isoformat") else str(rec.date)
        by_date[day].append((product, rec.quantity))

    orders_created = 0
    items_created = 0

    for day_str, lines in sorted(by_date.items()):
        closed_at = datetime.fromisoformat(day_str).replace(
            hour=12, minute=0, second=0, tzinfo=timezone.utc,
        )
        order = Order(
            type=OrderType.CONSUMPTION,
            status=OrderStatus.COMPLETED,
            created_by=actor.id,
            comment=payload.comment or "Импорт истории спроса",
            created_at=closed_at,
            closed_at=closed_at,
        )
        db.add(order)
        await db.flush()

        for product, qty in lines:
            db.add(OrderItem(
                order_id=order.id,
                product_id=product.id,
                cell_id=None,
                quantity=int(qty),
            ))
            items_created += 1
        orders_created += 1

    db.add(AuditLog(
        user_id=actor.id,
        action="IMPORT_DEMAND_HISTORY",
        entity="Order",
        detail={
            "orders": orders_created,
            "items": items_created,
            "days": len(by_date),
            "skus": len(skus),
        },
    ))
    await db.commit()

    return DemandHistoryImportResult(
        orders_created=orders_created,
        items_created=items_created,
        days_covered=len(by_date),
        skus=len(skus),
    )
