"""
Импорт приёмок, расходов и инвентаризаций с датами (генератор данных).
"""

from datetime import datetime, time, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    AuditLog,
    InventoryTask,
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    Product,
    Stock,
    User,
)
from app.schemas.bootstrap import BootstrapTimedOrder, BootstrapTimedOrdersResult
from app.services.cell_resolve import load_cells_maps, resolve_cell
from app.services.warehouse_service import (
    WarehouseService,
    add_stock_to_cell,
    get_cells_for_consumption,
)


def _dt_on_day(day) -> datetime:
    if hasattr(day, "year"):
        d = day
    else:
        d = datetime.fromisoformat(str(day)).date()
    return datetime.combine(d, time(hour=10, minute=0), tzinfo=timezone.utc)


async def _get_or_create_stock(product_id: int, cell_id: int, db: AsyncSession) -> Stock:
    res = await db.execute(
        select(Stock).where(Stock.product_id == product_id, Stock.cell_id == cell_id)
    )
    stock = res.scalar_one_or_none()
    if stock:
        return stock
    stock = Stock(product_id=product_id, cell_id=cell_id, quantity=0)
    db.add(stock)
    await db.flush()
    return stock


async def import_timed_orders(
    orders: list[BootstrapTimedOrder],
    db: AsyncSession,
    actor: User,
) -> BootstrapTimedOrdersResult:
    if not orders:
        return BootstrapTimedOrdersResult()

    pres = await db.execute(select(Product))
    products_by_sku = {p.sku.upper(): p for p in pres.scalars().all()}
    by_address, by_key = await load_cells_maps(db)

    arrivals = 0
    consumptions = 0
    inventories = 0
    moves = 0
    arrival_items = 0
    consumption_items = 0
    inventory_items = 0
    warnings: list[str] = []

    type_sort = {"ARRIVAL": 0, "MOVE": 1, "CONSUMPTION": 2, "INVENTORY": 3}
    sorted_orders = sorted(
        orders,
        key=lambda o: (_dt_on_day(o.date), type_sort.get(o.type, 9)),
    )

    for o in sorted_orders:
        closed_at = _dt_on_day(o.date)
        if o.type == "ARRIVAL":
            order = Order(
                type=OrderType.ARRIVAL,
                status=OrderStatus.COMPLETED,
                created_by=actor.id,
                comment=o.comment or "Приёмка (симуляция)",
                created_at=closed_at,
                closed_at=closed_at.replace(hour=14),
            )
            db.add(order)
            await db.flush()

            for i, line in enumerate(o.items, start=1):
                product = products_by_sku.get(line.sku.upper())
                if not product:
                    warnings.append(f"Приёмка {o.date}: SKU «{line.sku}» не найден")
                    continue
                cell = resolve_cell(line, by_address, by_key)
                if not cell:
                    warnings.append(f"Приёмка {o.date}: ячейка «{line.cell_address}» не найдена")
                    continue
                if not cell.is_active:
                    cell.is_active = True
                qty = int(line.quantity)
                added, warn = await add_stock_to_cell(cell, product.id, qty, db)
                if warn:
                    warnings.append(f"Приёмка {o.date}: {warn}")
                if added <= 0:
                    continue
                db.add(OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    cell_id=cell.id,
                    quantity=added,
                ))
                arrival_items += 1
            arrivals += 1

        elif o.type == "CONSUMPTION":
            order = Order(
                type=OrderType.CONSUMPTION,
                status=OrderStatus.COMPLETED,
                created_by=actor.id,
                comment=o.comment or "Расход (симуляция)",
                created_at=closed_at,
                closed_at=closed_at.replace(hour=16),
            )
            db.add(order)
            await db.flush()

            for line in o.items:
                product = products_by_sku.get(line.sku.upper())
                if not product:
                    warnings.append(f"Расход {o.date}: SKU «{line.sku}» не найден")
                    continue
                qty = int(line.quantity)
                db.add(OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    cell_id=None,
                    quantity=qty,
                ))
                consumption_items += 1

                try:
                    cell_rows = await get_cells_for_consumption(product.id, qty, db)
                except Exception:
                    cell_rows = []
                remaining = qty
                for stock, _cell in cell_rows:
                    if remaining <= 0:
                        break
                    take = min(stock.quantity, remaining)
                    stock.quantity -= take
                    remaining -= take

            consumptions += 1

        elif o.type == "MOVE":
            if len(o.items) != 1:
                warnings.append(f"Перемещение {o.date}: ожидается одна позиция")
                continue
            line = o.items[0]
            product = products_by_sku.get(line.sku.upper())
            if not product:
                warnings.append(f"Перемещение {o.date}: SKU «{line.sku}» не найден")
                continue
            from_cell = resolve_cell(line, by_address, by_key)
            if not from_cell:
                warnings.append(f"Перемещение {o.date}: ячейка «{line.cell_address}» не найдена")
                continue
            to_ref = SimpleNamespace(
                cell_address=line.to_cell_address,
                cell_zone=line.to_cell_zone,
                cell_rack=line.to_cell_rack,
                cell_shelf=line.to_cell_shelf,
                cell_position=line.to_cell_position,
            )
            to_cell = resolve_cell(to_ref, by_address, by_key)
            if not to_cell:
                warnings.append(f"Перемещение {o.date}: ячейка «{line.to_cell_address}» не найдена")
                continue
            qty = int(line.quantity)
            res_from = await db.execute(
                select(Stock)
                .where(Stock.product_id == product.id, Stock.cell_id == from_cell.id)
                .with_for_update()
            )
            from_stock = res_from.scalar_one_or_none()
            available = int(from_stock.quantity) if from_stock else 0
            if available < qty:
                warnings.append(
                    f"Перемещение {o.date}: в {from_cell.address} только {available} ед. «{line.sku}»"
                )
                continue
            res_to_all = await db.execute(
                select(Stock).where(Stock.cell_id == to_cell.id).with_for_update()
            )
            to_stocks = res_to_all.scalars().all()
            used = sum(int(s.quantity) for s in to_stocks)
            free = int(to_cell.max_capacity) - used
            if free < qty:
                warnings.append(
                    f"Перемещение {o.date}: в {to_cell.address} свободно {free} ед."
                )
                continue
            to_stock = next((s for s in to_stocks if s.product_id == product.id), None)
            if not to_stock:
                to_stock = Stock(product_id=product.id, cell_id=to_cell.id, quantity=0)
                db.add(to_stock)
                await db.flush()
            from_stock.quantity -= qty
            to_stock.quantity += qty
            db.add(AuditLog(
                user_id=actor.id,
                action="MOVE_STOCK",
                entity="Stock",
                created_at=closed_at.replace(hour=15),
                detail={
                    "product_id": product.id,
                    "from_cell_id": from_cell.id,
                    "to_cell_id": to_cell.id,
                    "quantity": qty,
                },
            ))
            moves += 1

        elif o.type == "INVENTORY":
            closed_at = _dt_on_day(o.date).replace(hour=18, minute=0)
            stock_res = await db.execute(
                select(Stock)
                .options(selectinload(Stock.product))
                .options(selectinload(Stock.cell))
                .where(Stock.quantity > 0)
            )
            stocks = stock_res.scalars().all()
            if not stocks:
                warnings.append(f"Инвентаризация {o.date}: нет остатков для пересчёта")
                continue

            order = Order(
                type=OrderType.INVENTORY,
                status=OrderStatus.IN_PROGRESS,
                created_by=actor.id,
                comment=o.comment or "Инвентаризация (симуляция)",
                created_at=closed_at.replace(hour=10),
                closed_at=None,
            )
            db.add(order)
            await db.flush()

            for stock in stocks:
                db.add(OrderItem(
                    order_id=order.id,
                    product_id=stock.product_id,
                    cell_id=stock.cell_id,
                    quantity=int(stock.quantity),
                    quantity_fact=int(stock.quantity),
                ))
                inventory_items += 1

            await WarehouseService._create_inventory_tasks_from_stocks(
                order.id, stocks, db,
            )
            await db.flush()

            task_res = await db.execute(
                select(InventoryTask).where(InventoryTask.order_id == order.id)
            )
            now = closed_at
            for task in task_res.scalars().all():
                task.status = OrderStatus.COMPLETED
                task.started_by = actor.id
                task.started_at = now
                task.completed_at = now

            order.status = OrderStatus.COMPLETED
            order.closed_at = now
            inventories += 1

    db.add(AuditLog(
        user_id=actor.id,
        action="IMPORT_TIMED_ORDERS",
        entity="Order",
        detail={
            "arrivals": arrivals,
            "consumptions": consumptions,
            "inventories": inventories,
            "moves": moves,
            "arrival_items": arrival_items,
            "consumption_items": consumption_items,
            "inventory_items": inventory_items,
        },
    ))
    await db.commit()

    return BootstrapTimedOrdersResult(
        arrivals=arrivals,
        consumptions=consumptions,
        inventories=inventories,
        moves=moves,
        arrival_items=arrival_items,
        consumption_items=consumption_items,
        inventory_items=inventory_items,
        warnings=warnings[:50],
    )
