from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    AuditLog, InventoryTask, Order, OrderItem, OrderStatus, OrderType,
    Product, Stock, StorageCell, User,
)
from app.schemas.warehouse import (
    ArrivalComplete, ArrivalCreate, ConsumptionCreate, InventoryConfirm,
    InventoryCreate, InventoryDiscrepancyOut, InventoryLossSummaryOut,
    InventoryTaskOut, RouteSheet, RouteSheetItem,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _get_order_or_404(order_id: int, db: AsyncSession) -> Order:
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
        .options(selectinload(Order.items).selectinload(OrderItem.cell))
        .where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return order


async def get_cell_total_used(cell_id: int, db: AsyncSession) -> int:
    """Суммарное количество всех товаров в ячейке."""
    result = await db.execute(
        select(func.coalesce(func.sum(Stock.quantity), 0)).where(Stock.cell_id == cell_id)
    )
    return int(result.scalar() or 0)


async def add_stock_to_cell(
    cell: StorageCell,
    product_id: int,
    quantity: int,
    db: AsyncSession,
    *,
    strict: bool = False,
) -> tuple[int, Optional[str]]:
    """
    Размещает товар с учётом max_capacity ячейки (лимит на все SKU в ячейке).
    Возвращает (сколько реально добавлено, предупреждение или None).
    """
    if quantity <= 0:
        return 0, None

    used = await get_cell_total_used(cell.id, db)
    free = int(cell.max_capacity) - used
    if free <= 0:
        msg = (
            f"Ячейка {cell.address} переполнена: {used} / {cell.max_capacity} ед. "
            f"(лимит на все товары в ячейке)"
        )
        if strict:
            raise HTTPException(status_code=400, detail=msg)
        return 0, msg

    add_qty = min(int(quantity), free)
    stock = await _get_or_create_stock(product_id, cell.id, db)
    stock.quantity += add_qty

    warning = None
    if add_qty < quantity:
        warning = (
            f"Ячейка {cell.address}: принято {add_qty} из {quantity} ед. "
            f"(занято {used + add_qty} / {cell.max_capacity})"
        )
    return add_qty, warning


async def _get_or_create_stock(
    product_id: int, cell_id: int, db: AsyncSession
) -> Stock:
    """Возвращает запись Stock, создаёт если не существует."""
    result = await db.execute(
        select(Stock)
        .where(Stock.product_id == product_id, Stock.cell_id == cell_id)
        .with_for_update()          # SELECT FOR UPDATE — защита от race condition
    )
    stock = result.scalar_one_or_none()
    if not stock:
        stock = Stock(product_id=product_id, cell_id=cell_id, quantity=0)
        db.add(stock)
        await db.flush()
    return stock


# ─── Cell Selection Algorithm ─────────────────────────────────────────────────

async def find_best_cell(
    product_id: int, quantity: int, db: AsyncSession
) -> Optional[StorageCell]:
    """
    Алгоритм выбора ячейки для приёмки:
    1. Ячейки, где этот товар уже есть и есть место (консолидация)
    2. Пустые ячейки с достаточной вместимостью
    Сортировка: зона → стеллаж → полка → позиция (кратчайший путь).
    """
    # Текущая загрузка каждой ячейки
    cell_load_sq = (
        select(
            Stock.cell_id,
            func.coalesce(func.sum(Stock.quantity), 0).label("used"),
        )
        .group_by(Stock.cell_id)
        .subquery()
    )

    base_q = (
        select(StorageCell, func.coalesce(cell_load_sq.c.used, 0).label("used"))
        .outerjoin(cell_load_sq, cell_load_sq.c.cell_id == StorageCell.id)
        .where(StorageCell.is_active.is_(True))
        .where(
            StorageCell.max_capacity - func.coalesce(cell_load_sq.c.used, 0) >= quantity
        )
        .order_by(StorageCell.zone, StorageCell.rack, StorageCell.shelf, StorageCell.position)
    )

    # Сначала ищем ячейки с этим товаром
    with_product_q = (
        base_q
        .join(Stock, (Stock.cell_id == StorageCell.id) & (Stock.product_id == product_id))
        .where(Stock.quantity > 0)
    )
    result = await db.execute(with_product_q.limit(1))
    row = result.first()
    if row:
        return row[0]

    # Затем любую подходящую
    result = await db.execute(base_q.limit(1))
    row = result.first()
    return row[0] if row else None


# ─── Stock Query ──────────────────────────────────────────────────────────────

async def get_cells_for_consumption(
    product_id: int, needed_qty: int, db: AsyncSession
) -> list[tuple[Stock, StorageCell]]:
    """
    Возвращает список (Stock, Cell) для списания товара.
    FIFO по адресу ячейки. Сначала берём из ячеек с наименьшим адресом.
    """
    result = await db.execute(
        select(Stock, StorageCell)
        .join(StorageCell, StorageCell.id == Stock.cell_id)
        .where(Stock.product_id == product_id, Stock.quantity > 0)
        .order_by(StorageCell.zone, StorageCell.rack, StorageCell.shelf, StorageCell.position)
        .with_for_update()
    )
    rows = result.all()

    selected: list[tuple[Stock, StorageCell]] = []
    remaining = needed_qty
    for stock, cell in rows:
        if remaining <= 0:
            break
        selected.append((stock, cell))
        remaining -= stock.quantity

    if remaining > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Недостаточно товара на складе. Не хватает: {remaining} ед.",
        )
    return selected


async def _get_available_stock(product_id: int, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(Stock.quantity), 0)).where(
            Stock.product_id == product_id,
            Stock.quantity > 0,
        )
    )
    return int(result.scalar_one())


# ─── Arrival (Приёмка) ────────────────────────────────────────────────────────

class WarehouseService:

    @staticmethod
    async def create_arrival(
        data: ArrivalCreate, db: AsyncSession, actor: User
    ) -> Order:
        order = Order(
            type=OrderType.ARRIVAL,
            status=OrderStatus.IN_PROGRESS,
            created_by=actor.id,
            comment=data.comment,
        )
        db.add(order)
        await db.flush()

        for item_data in data.items:
            # Проверяем товар
            product = await db.get(Product, item_data.product_id)
            if not product or not product.is_active:
                raise HTTPException(
                    status_code=404,
                    detail=f"Товар ID={item_data.product_id} не найден",
                )

            # Определяем ячейку
            if item_data.cell_id:
                cell = await db.get(StorageCell, item_data.cell_id)
                if not cell or not cell.is_active:
                    raise HTTPException(status_code=404, detail="Ячейка не найдена")
            else:
                cell = await find_best_cell(item_data.product_id, item_data.quantity, db)
                if not cell:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Нет подходящей ячейки для товара {product.sku} (кол-во: {item_data.quantity})",
                    )

            # Добавляем позицию заказа
            order_item = OrderItem(
                order_id=order.id,
                product_id=item_data.product_id,
                cell_id=cell.id,
                quantity=item_data.quantity,
            )
            db.add(order_item)

            # Обновляем остаток
            stock = await _get_or_create_stock(item_data.product_id, cell.id, db)
            stock.quantity += item_data.quantity

        order.status = OrderStatus.COMPLETED
        order.closed_at = _now()

        db.add(AuditLog(
            user_id=actor.id,
            action="ARRIVAL",
            entity="Order",
            entity_id=str(order.id),
            detail={"items_count": len(data.items)},
        ))
        await db.commit()
        return await _get_order_or_404(order.id, db)

    @staticmethod
    async def create_arrival_request(
        data: ArrivalCreate, db: AsyncSession, actor: User
    ) -> Order:
        """Формирует заказ на приёмку без изменения остатков."""
        order = Order(
            type=OrderType.ARRIVAL,
            status=OrderStatus.PENDING,
            created_by=actor.id,
            comment=data.comment,
        )
        db.add(order)
        await db.flush()

        for item_data in data.items:
            product = await db.get(Product, item_data.product_id)
            if not product or not product.is_active:
                raise HTTPException(
                    status_code=404,
                    detail=f"Товар ID={item_data.product_id} не найден",
                )

            if item_data.cell_id:
                cell = await db.get(StorageCell, item_data.cell_id)
                if not cell or not cell.is_active:
                    raise HTTPException(status_code=404, detail="Ячейка не найдена")

            db.add(OrderItem(
                order_id=order.id,
                product_id=item_data.product_id,
                cell_id=item_data.cell_id,
                quantity=item_data.quantity,
            ))

        db.add(AuditLog(
            user_id=actor.id,
            action="ARRIVAL_REQUEST_CREATED",
            entity="Order",
            entity_id=str(order.id),
            detail={"items_count": len(data.items)},
        ))
        await db.commit()
        return await _get_order_or_404(order.id, db)

    @staticmethod
    async def start_arrival(
        order_id: int, db: AsyncSession, actor: User
    ) -> Order:
        order = await _get_order_or_404(order_id, db)
        if order.type != OrderType.ARRIVAL:
            raise HTTPException(status_code=400, detail="Заказ не является приёмкой")
        if order.status == OrderStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Заказ уже завершён")
        if order.status == OrderStatus.CANCELLED:
            raise HTTPException(status_code=400, detail="Заказ отменён")
        if order.status == OrderStatus.IN_PROGRESS:
            return order
        if order.status != OrderStatus.PENDING:
            raise HTTPException(status_code=400, detail="Заказ нельзя взять в работу")

        order.status = OrderStatus.IN_PROGRESS
        db.add(AuditLog(
            user_id=actor.id,
            action="ARRIVAL_STARTED",
            entity="Order",
            entity_id=str(order_id),
        ))
        await db.commit()
        return await _get_order_or_404(order_id, db)

    @staticmethod
    async def complete_arrival(
        order_id: int, data: ArrivalComplete, db: AsyncSession, actor: User
    ) -> Order:
        """Кладовщик размещает товар по ячейкам и завершает приёмку."""
        order = await _get_order_or_404(order_id, db)
        if order.type != OrderType.ARRIVAL:
            raise HTTPException(status_code=400, detail="Заказ не является приёмкой")
        if order.status == OrderStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Заказ уже завершён")
        if order.status == OrderStatus.CANCELLED:
            raise HTTPException(status_code=400, detail="Заказ отменён")
        if order.status == OrderStatus.PENDING:
            order.status = OrderStatus.IN_PROGRESS

        items_by_id = {item.id: item for item in order.items}
        if not items_by_id:
            raise HTTPException(status_code=400, detail="В заказе нет позиций")

        for fact in data.items:
            item = items_by_id.get(fact.order_item_id)
            if not item:
                raise HTTPException(
                    status_code=404,
                    detail=f"Позиция ID={fact.order_item_id} не найдена в этом заказе",
                )

            product = await db.get(Product, item.product_id)
            if not product or not product.is_active:
                raise HTTPException(status_code=404, detail=f"Товар ID={item.product_id} не найден")

            cell_id = fact.cell_id or item.cell_id
            if cell_id:
                cell = await db.get(StorageCell, cell_id)
                if not cell or not cell.is_active:
                    raise HTTPException(status_code=404, detail="Ячейка не найдена")
            else:
                cell = await find_best_cell(item.product_id, fact.quantity, db)
                if not cell:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Нет подходящей ячейки для товара {product.sku}",
                    )

            item.cell_id = cell.id
            added, warn = await add_stock_to_cell(cell, item.product_id, fact.quantity, db, strict=False)
            if added <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=warn or f"Нет свободного места в ячейке {cell.address}",
                )
            item.quantity = added

        order.status = OrderStatus.COMPLETED
        order.closed_at = _now()

        db.add(AuditLog(
            user_id=actor.id,
            action="ARRIVAL_COMPLETED",
            entity="Order",
            entity_id=str(order_id),
            detail={"items_count": len(data.items)},
        ))
        await db.commit()
        return await _get_order_or_404(order_id, db)

    # ─── Consumption (Расход) ─────────────────────────────────────────────────

    @staticmethod
    async def create_consumption(
        data: ConsumptionCreate, db: AsyncSession, actor: User
    ) -> Order:
        order = Order(
            type=OrderType.CONSUMPTION,
            status=OrderStatus.PENDING,
            created_by=actor.id,
            comment=data.comment,
        )
        db.add(order)
        await db.flush()

        all_route_items: list[OrderItem] = []

        for item_data in data.items:
            product = await db.get(Product, item_data.product_id)
            if not product:
                raise HTTPException(status_code=404, detail=f"Товар ID={item_data.product_id} не найден")

            # Получаем ячейки для списания (с SELECT FOR UPDATE)
            cell_rows = await get_cells_for_consumption(
                item_data.product_id, item_data.quantity, db
            )

            remaining = item_data.quantity
            for stock, cell in cell_rows:
                take = min(stock.quantity, remaining)

                oi = OrderItem(
                    order_id=order.id,
                    product_id=item_data.product_id,
                    cell_id=cell.id,
                    quantity=take,
                )
                db.add(oi)
                all_route_items.append((oi, cell))

                stock.quantity -= take
                remaining -= take
                if remaining <= 0:
                    break

        order.status = OrderStatus.IN_PROGRESS

        db.add(AuditLog(
            user_id=actor.id,
            action="CONSUMPTION_CREATED",
            entity="Order",
            entity_id=str(order.id),
        ))
        await db.commit()
        return await _get_order_or_404(order.id, db)

    @staticmethod
    async def create_consumption_request(
        data: ConsumptionCreate, db: AsyncSession, actor: User
    ) -> Order:
        """
        Формирует заказ на расход без списания остатков.
        Кладовщик выполняет его позже через start_consumption.
        """
        order = Order(
            type=OrderType.CONSUMPTION,
            status=OrderStatus.PENDING,
            created_by=actor.id,
            comment=data.comment,
        )
        db.add(order)
        await db.flush()

        for item_data in data.items:
            product = await db.get(Product, item_data.product_id)
            if not product or not product.is_active:
                raise HTTPException(
                    status_code=404,
                    detail=f"Товар ID={item_data.product_id} не найден",
                )

            available = await _get_available_stock(item_data.product_id, db)
            if available < item_data.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Недостаточно товара «{product.sku}» на складе. "
                        f"Доступно: {available} ед., запрошено: {item_data.quantity} ед."
                    ),
                )

            db.add(OrderItem(
                order_id=order.id,
                product_id=item_data.product_id,
                cell_id=None,
                quantity=item_data.quantity,
            ))

        db.add(AuditLog(
            user_id=actor.id,
            action="CONSUMPTION_REQUEST_CREATED",
            entity="Order",
            entity_id=str(order.id),
            detail={"items_count": len(data.items)},
        ))
        await db.commit()
        return await _get_order_or_404(order.id, db)

    @staticmethod
    async def start_consumption(
        order_id: int, db: AsyncSession, actor: User
    ) -> Order:
        """Кладовщик берёт заказ в работу: распределяет по ячейкам и резервирует остатки."""
        order = await _get_order_or_404(order_id, db)
        if order.type != OrderType.CONSUMPTION:
            raise HTTPException(status_code=400, detail="Заказ не является расходом")
        if order.status == OrderStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Заказ уже завершён")
        if order.status == OrderStatus.CANCELLED:
            raise HTTPException(status_code=400, detail="Заказ отменён")
        if order.status == OrderStatus.IN_PROGRESS:
            return order

        if order.status != OrderStatus.PENDING:
            raise HTTPException(status_code=400, detail="Заказ нельзя взять в работу")

        if not order.items:
            raise HTTPException(status_code=400, detail="В заказе нет позиций")

        if any(it.cell_id is not None for it in order.items):
            raise HTTPException(status_code=400, detail="Заказ уже подготовлен к выполнению")

        requested: dict[int, int] = {}
        for it in order.items:
            requested[it.product_id] = requested.get(it.product_id, 0) + int(it.quantity)

        for item in list(order.items):
            await db.delete(item)
        await db.flush()

        for product_id, qty in requested.items():
            cell_rows = await get_cells_for_consumption(product_id, qty, db)
            remaining = qty
            for stock, cell in cell_rows:
                take = min(stock.quantity, remaining)
                db.add(OrderItem(
                    order_id=order.id,
                    product_id=product_id,
                    cell_id=cell.id,
                    quantity=take,
                ))
                stock.quantity -= take
                remaining -= take
                if remaining <= 0:
                    break

        order.status = OrderStatus.IN_PROGRESS

        db.add(AuditLog(
            user_id=actor.id,
            action="CONSUMPTION_STARTED",
            entity="Order",
            entity_id=str(order_id),
            detail={"items_count": len(requested)},
        ))
        await db.commit()
        return await _get_order_or_404(order_id, db)

    @staticmethod
    async def complete_consumption(
        order_id: int, db: AsyncSession, actor: User
    ) -> Order:
        order = await _get_order_or_404(order_id, db)
        if order.type != OrderType.CONSUMPTION:
            raise HTTPException(status_code=400, detail="Заказ не является расходом")
        if order.status == OrderStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Заказ уже завершён")

        order.status = OrderStatus.COMPLETED
        order.closed_at = _now()
        db.add(AuditLog(
            user_id=actor.id,
            action="CONSUMPTION_COMPLETED",
            entity="Order",
            entity_id=str(order_id),
        ))
        await db.commit()
        return await _get_order_or_404(order_id, db)

    @staticmethod
    async def get_route_sheet(order_id: int, db: AsyncSession) -> RouteSheet:
        """Маршрутный лист — отсортированный список ячеек для обхода."""
        order = await _get_order_or_404(order_id, db)
        if order.type not in (OrderType.CONSUMPTION, OrderType.INVENTORY):
            raise HTTPException(
                status_code=400,
                detail="Маршрутный лист доступен для расхода и инвентаризации",
            )

        items_sorted = sorted(
            order.items,
            key=lambda i: (
                i.cell.zone if i.cell else "Z",
                i.cell.rack if i.cell else 999,
                i.cell.shelf if i.cell else 999,
                i.cell.position if i.cell else 999,
            ),
        )

        route = []
        for step, item in enumerate(items_sorted, 1):
            cell = item.cell
            route.append(RouteSheetItem(
                step=step,
                order_item_id=item.id,
                cell_address=cell.address if cell else "—",
                zone=cell.zone if cell else "",
                rack=cell.rack if cell else 0,
                shelf=cell.shelf if cell else 0,
                position=cell.position if cell else 0,
                product_sku=item.product.sku if item.product else "",
                product_name=item.product.name if item.product else "",
                quantity=item.quantity,
                quantity_fact=item.quantity_fact,
            ))

        return RouteSheet(order_id=order_id, total_items=len(route), route=route)

    # ─── Inventory (Инвентаризация) ───────────────────────────────────────────

    @staticmethod
    def _inventory_task_item_ids(order: Order, task: InventoryTask) -> list[int]:
        ids = []
        for it in order.items:
            if not it.cell_id or not it.cell:
                continue
            if it.cell.zone == task.zone and it.cell.rack == task.rack:
                ids.append(it.id)
        return ids

    @staticmethod
    async def _create_inventory_tasks_from_stocks(
        order_id: int, stocks: list[Stock], db: AsyncSession
    ) -> int:
        """Создаёт подзадания по стеллажам из уже загруженных остатков (без lazy-load)."""
        racks: set[tuple[str, int]] = set()
        for stock in stocks:
            if stock.cell:
                racks.add((stock.cell.zone, stock.cell.rack))
        for zone, rack in sorted(racks, key=lambda x: (x[0], x[1])):
            db.add(InventoryTask(
                order_id=order_id,
                zone=zone,
                rack=rack,
                status=OrderStatus.PENDING,
            ))
        return len(racks)

    @staticmethod
    async def _create_inventory_tasks_for_order(order_id: int, db: AsyncSession) -> int:
        """Создаёт подзадания по позициям заказа (явная загрузка ячеек)."""
        res = await db.execute(
            select(OrderItem)
            .options(selectinload(OrderItem.cell))
            .where(OrderItem.order_id == order_id)
        )
        racks: set[tuple[str, int]] = set()
        for it in res.scalars().all():
            if it.cell:
                racks.add((it.cell.zone, it.cell.rack))
        for zone, rack in sorted(racks, key=lambda x: (x[0], x[1])):
            db.add(InventoryTask(
                order_id=order_id,
                zone=zone,
                rack=rack,
                status=OrderStatus.PENDING,
            ))
        return len(racks)

    @staticmethod
    async def _ensure_inventory_tasks(order: Order, db: AsyncSession) -> list[InventoryTask]:
        """Для старых заказов без подзаданий — создать их из позиций."""
        res = await db.execute(
            select(InventoryTask)
            .where(InventoryTask.order_id == order.id)
            .order_by(InventoryTask.zone, InventoryTask.rack)
        )
        tasks = list(res.scalars().all())
        if tasks:
            return tasks
        await WarehouseService._create_inventory_tasks_for_order(order.id, db)
        await db.flush()
        res = await db.execute(
            select(InventoryTask)
            .where(InventoryTask.order_id == order.id)
            .order_by(InventoryTask.zone, InventoryTask.rack)
        )
        return list(res.scalars().all())

    @staticmethod
    def _task_stats(order: Order, task: InventoryTask) -> dict:
        item_ids = WarehouseService._inventory_task_item_ids(order, task)
        items = [it for it in order.items if it.id in item_ids]
        loss_units = 0
        surplus_units = 0
        counted = 0
        for it in items:
            if it.quantity_fact is None:
                continue
            counted += 1
            delta = int(it.quantity_fact) - int(it.quantity)
            if delta < 0:
                loss_units += -delta
            elif delta > 0:
                surplus_units += delta
        return {
            "items_total": len(items),
            "items_counted": counted,
            "loss_units": loss_units,
            "surplus_units": surplus_units,
        }

    @staticmethod
    async def _sync_parent_inventory_status(order: Order, db: AsyncSession) -> None:
        tasks = await WarehouseService._ensure_inventory_tasks(order, db)
        if not tasks:
            return
        statuses = {t.status for t in tasks}
        if statuses == {OrderStatus.COMPLETED}:
            order.status = OrderStatus.COMPLETED
            if not order.closed_at:
                order.closed_at = _now()
        elif OrderStatus.IN_PROGRESS in statuses or OrderStatus.COMPLETED in statuses:
            order.status = OrderStatus.IN_PROGRESS
        elif statuses == {OrderStatus.PENDING}:
            order.status = OrderStatus.PENDING

    @staticmethod
    def _inventory_discrepancies(order: Order) -> list[InventoryDiscrepancyOut]:
        rows: list[InventoryDiscrepancyOut] = []
        for it in order.items:
            if it.quantity_fact is None:
                continue
            delta = int(it.quantity_fact) - int(it.quantity)
            if delta == 0:
                continue
            cell = it.cell
            rows.append(InventoryDiscrepancyOut(
                order_item_id=it.id,
                product_sku=it.product.sku if it.product else "",
                product_name=it.product.name if it.product else "",
                cell_address=cell.address if cell else "—",
                zone=cell.zone if cell else "",
                rack=cell.rack if cell else 0,
                expected=int(it.quantity),
                fact=int(it.quantity_fact),
                delta=delta,
                kind="loss" if delta < 0 else "surplus",
            ))
        rows.sort(key=lambda r: (r.zone, r.rack, r.cell_address))
        return rows

    @staticmethod
    async def create_inventory_request(
        data: InventoryCreate, db: AsyncSession, actor: User
    ) -> Order:
        """Формирует задание на пересчёт (PENDING). Остатки не меняются до завершения."""
        order = Order(
            type=OrderType.INVENTORY,
            status=OrderStatus.PENDING,
            created_by=actor.id,
            comment=data.comment,
        )
        db.add(order)
        await db.flush()

        stock_q = (
            select(Stock)
            .options(selectinload(Stock.product))
            .options(selectinload(Stock.cell))
            .where(Stock.quantity > 0)
        )
        if data.product_ids:
            stock_q = stock_q.where(Stock.product_id.in_(data.product_ids))

        result = await db.execute(stock_q)
        stocks = result.scalars().all()

        if not stocks:
            raise HTTPException(status_code=400, detail="Нет товаров для инвентаризации")

        for stock in stocks:
            db.add(OrderItem(
                order_id=order.id,
                product_id=stock.product_id,
                cell_id=stock.cell_id,
                quantity=stock.quantity,
                quantity_fact=None,
            ))

        tasks_count = await WarehouseService._create_inventory_tasks_from_stocks(
            order.id, stocks, db
        )

        db.add(AuditLog(
            user_id=actor.id,
            action="INVENTORY_REQUEST_CREATED",
            entity="Order",
            entity_id=str(order.id),
            detail={"items_count": len(stocks), "tasks_count": tasks_count},
        ))
        await db.commit()
        return await _get_order_or_404(order.id, db)

    @staticmethod
    async def create_inventory(
        data: InventoryCreate, db: AsyncSession, actor: User
    ) -> Order:
        """Алиас для обратной совместимости API."""
        return await WarehouseService.create_inventory_request(data, db, actor)

    @staticmethod
    async def start_inventory(order_id: int, db: AsyncSession, actor: User) -> Order:
        order = await _get_order_or_404(order_id, db)
        if order.type != OrderType.INVENTORY:
            raise HTTPException(status_code=400, detail="Заказ не является инвентаризацией")
        if order.status == OrderStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Инвентаризация уже завершена")
        if order.status == OrderStatus.CANCELLED:
            raise HTTPException(status_code=400, detail="Инвентаризация отменена")
        if order.status == OrderStatus.IN_PROGRESS:
            return order
        if order.status != OrderStatus.PENDING:
            raise HTTPException(status_code=400, detail="Инвентаризацию нельзя взять в работу")

        if not order.items:
            raise HTTPException(status_code=400, detail="В задании нет позиций")

        order.status = OrderStatus.IN_PROGRESS
        db.add(AuditLog(
            user_id=actor.id,
            action="INVENTORY_STARTED",
            entity="Order",
            entity_id=str(order_id),
        ))
        await db.commit()
        return await _get_order_or_404(order_id, db)

    @staticmethod
    async def _apply_inventory_facts(
        order: Order,
        data: InventoryConfirm,
        db: AsyncSession,
        *,
        required_item_ids: Optional[set[int]] = None,
    ) -> list[dict]:
        items_by_id = {item.id: item for item in order.items}
        fact_ids = {f.order_item_id for f in data.fact_items}

        if len(fact_ids) != len(data.fact_items):
            raise HTTPException(status_code=400, detail="Дублирующиеся позиции в fact_items")

        scope_items = order.items
        if required_item_ids is not None:
            scope_items = [it for it in order.items if it.id in required_item_ids]
            for fact in data.fact_items:
                if fact.order_item_id not in required_item_ids:
                    raise HTTPException(
                        status_code=400,
                        detail="Позиция не относится к выбранному стеллажу",
                    )

        missing = [it.id for it in scope_items if it.id not in fact_ids]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Не указаны фактические данные для {len(missing)} позиций",
            )

        corrections = []
        for fact in data.fact_items:
            item = items_by_id.get(fact.order_item_id)
            if not item:
                raise HTTPException(
                    status_code=404,
                    detail=f"Позиция ID={fact.order_item_id} не найдена в этом заказе",
                )
            item.quantity_fact = fact.quantity_fact
            delta = fact.quantity_fact - item.quantity

            if delta != 0:
                stock = await _get_or_create_stock(item.product_id, item.cell_id, db)
                stock.quantity = max(0, stock.quantity + delta)
                corrections.append({
                    "product_id": item.product_id,
                    "cell_id": item.cell_id,
                    "expected": item.quantity,
                    "fact": fact.quantity_fact,
                    "delta": delta,
                })

        return corrections

    @staticmethod
    async def list_inventory_tasks(order_id: int, db: AsyncSession) -> list[InventoryTaskOut]:
        order = await _get_order_or_404(order_id, db)
        if order.type != OrderType.INVENTORY:
            raise HTTPException(status_code=400, detail="Заказ не является инвентаризацией")
        tasks = await WarehouseService._ensure_inventory_tasks(order, db)
        out = []
        for task in tasks:
            st = WarehouseService._task_stats(order, task)
            out.append(InventoryTaskOut(
                id=task.id,
                order_id=order.id,
                zone=task.zone,
                rack=task.rack,
                label=task.label,
                status=task.status,
                **st,
            ))
        return out

    @staticmethod
    async def start_inventory_task(
        order_id: int, task_id: int, db: AsyncSession, actor: User
    ) -> InventoryTaskOut:
        order = await _get_order_or_404(order_id, db)
        if order.type != OrderType.INVENTORY:
            raise HTTPException(status_code=400, detail="Заказ не является инвентаризацией")
        if order.status == OrderStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Инвентаризация уже завершена")
        if order.status == OrderStatus.CANCELLED:
            raise HTTPException(status_code=400, detail="Инвентаризация отменена")

        task = await db.get(InventoryTask, task_id)
        if not task or task.order_id != order.id:
            raise HTTPException(status_code=404, detail="Подзадание не найдено")
        if task.status == OrderStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Стеллаж уже пересчитан")
        if task.status == OrderStatus.CANCELLED:
            raise HTTPException(status_code=400, detail="Подзадание отменено")

        if task.status == OrderStatus.PENDING:
            task.status = OrderStatus.IN_PROGRESS
            task.started_by = actor.id
            task.started_at = _now()
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.IN_PROGRESS

        db.add(AuditLog(
            user_id=actor.id,
            action="INVENTORY_TASK_STARTED",
            entity="InventoryTask",
            entity_id=str(task.id),
            detail={"order_id": order_id, "zone": task.zone, "rack": task.rack},
        ))
        await db.commit()
        st = WarehouseService._task_stats(order, task)
        return InventoryTaskOut(
            id=task.id,
            order_id=order.id,
            zone=task.zone,
            rack=task.rack,
            label=task.label,
            status=task.status,
            **st,
        )

    @staticmethod
    async def get_inventory_task_route(
        order_id: int, task_id: int, db: AsyncSession
    ) -> RouteSheet:
        order = await _get_order_or_404(order_id, db)
        task = await db.get(InventoryTask, task_id)
        if not task or task.order_id != order.id:
            raise HTTPException(status_code=404, detail="Подзадание не найдено")

        item_ids = set(WarehouseService._inventory_task_item_ids(order, task))
        items_sorted = sorted(
            [it for it in order.items if it.id in item_ids],
            key=lambda i: (
                i.cell.shelf if i.cell else 999,
                i.cell.position if i.cell else 999,
            ),
        )

        route = []
        for step, item in enumerate(items_sorted, 1):
            cell = item.cell
            route.append(RouteSheetItem(
                step=step,
                order_item_id=item.id,
                cell_address=cell.address if cell else "—",
                zone=cell.zone if cell else "",
                rack=cell.rack if cell else 0,
                shelf=cell.shelf if cell else 0,
                position=cell.position if cell else 0,
                product_sku=item.product.sku if item.product else "",
                product_name=item.product.name if item.product else "",
                quantity=item.quantity,
                quantity_fact=item.quantity_fact,
            ))

        return RouteSheet(order_id=order_id, total_items=len(route), route=route)

    @staticmethod
    async def complete_inventory_task(
        order_id: int,
        task_id: int,
        data: InventoryConfirm,
        db: AsyncSession,
        actor: User,
    ) -> InventoryTaskOut:
        order = await _get_order_or_404(order_id, db)
        if order.type != OrderType.INVENTORY:
            raise HTTPException(status_code=400, detail="Заказ не является инвентаризацией")
        if order.status == OrderStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Инвентаризация уже завершена")
        if order.status == OrderStatus.CANCELLED:
            raise HTTPException(status_code=400, detail="Инвентаризация отменена")

        task = await db.get(InventoryTask, task_id)
        if not task or task.order_id != order.id:
            raise HTTPException(status_code=404, detail="Подзадание не найдено")
        if task.status == OrderStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Стеллаж уже пересчитан")

        if task.status == OrderStatus.PENDING:
            task.status = OrderStatus.IN_PROGRESS
            task.started_by = actor.id
            task.started_at = _now()
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.IN_PROGRESS

        required_ids = set(WarehouseService._inventory_task_item_ids(order, task))
        if not required_ids:
            raise HTTPException(status_code=400, detail="В подзадании нет позиций")

        corrections = await WarehouseService._apply_inventory_facts(
            order, data, db, required_item_ids=required_ids,
        )

        task.status = OrderStatus.COMPLETED
        task.completed_at = _now()
        await WarehouseService._sync_parent_inventory_status(order, db)

        loss_units = sum(-c["delta"] for c in corrections if c["delta"] < 0)
        surplus_units = sum(c["delta"] for c in corrections if c["delta"] > 0)

        db.add(AuditLog(
            user_id=actor.id,
            action="INVENTORY_TASK_COMPLETED",
            entity="InventoryTask",
            entity_id=str(task.id),
            detail={
                "order_id": order_id,
                "zone": task.zone,
                "rack": task.rack,
                "corrections": len(corrections),
                "loss_units": loss_units,
                "surplus_units": surplus_units,
            },
        ))
        await db.commit()

        order = await _get_order_or_404(order_id, db)
        task = await db.get(InventoryTask, task_id)
        st = WarehouseService._task_stats(order, task)
        return InventoryTaskOut(
            id=task.id,
            order_id=order.id,
            zone=task.zone,
            rack=task.rack,
            label=task.label,
            status=task.status,
            **st,
        )

    @staticmethod
    async def get_inventory_losses(
        order_id: int, db: AsyncSession
    ) -> InventoryLossSummaryOut:
        order = await _get_order_or_404(order_id, db)
        if order.type != OrderType.INVENTORY:
            raise HTTPException(status_code=400, detail="Заказ не является инвентаризацией")

        tasks = await WarehouseService._ensure_inventory_tasks(order, db)
        discrepancies = WarehouseService._inventory_discrepancies(order)
        total_loss = sum(-d.delta for d in discrepancies if d.delta < 0)
        total_surplus = sum(d.delta for d in discrepancies if d.delta > 0)
        tasks_completed = sum(1 for t in tasks if t.status == OrderStatus.COMPLETED)

        return InventoryLossSummaryOut(
            order_id=order.id,
            status=order.status,
            tasks_total=len(tasks),
            tasks_completed=tasks_completed,
            total_loss_units=total_loss,
            total_surplus_units=total_surplus,
            discrepancies=discrepancies,
        )

    @staticmethod
    async def complete_inventory(
        order_id: int, data: InventoryConfirm, db: AsyncSession, actor: User
    ) -> Order:
        """Завершение пересчёта: фактические количества и корректировка остатков."""
        order = await _get_order_or_404(order_id, db)
        if order.type != OrderType.INVENTORY:
            raise HTTPException(status_code=400, detail="Заказ не является инвентаризацией")
        if order.status == OrderStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Инвентаризация уже завершена")
        if order.status == OrderStatus.CANCELLED:
            raise HTTPException(status_code=400, detail="Инвентаризация отменена")
        if order.status == OrderStatus.PENDING:
            order.status = OrderStatus.IN_PROGRESS

        tasks = await WarehouseService._ensure_inventory_tasks(order, db)
        incomplete = [t for t in tasks if t.status != OrderStatus.COMPLETED]
        if incomplete:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Сначала завершите пересчёт всех стеллажей "
                    f"({len(incomplete)} из {len(tasks)} осталось)"
                ),
            )

        pending_facts = [it.id for it in order.items if it.quantity_fact is None]
        if pending_facts:
            corrections = await WarehouseService._apply_inventory_facts(order, data, db)
        else:
            corrections = []

        order.status = OrderStatus.COMPLETED
        order.closed_at = _now()
        for t in tasks:
            if t.status != OrderStatus.COMPLETED:
                t.status = OrderStatus.COMPLETED
                t.completed_at = _now()

        loss_units = sum(-c["delta"] for c in corrections if c["delta"] < 0)

        db.add(AuditLog(
            user_id=actor.id,
            action="INVENTORY_COMPLETED",
            entity="Order",
            entity_id=str(order_id),
            detail={"corrections": len(corrections), "loss_units": loss_units},
        ))
        await db.commit()
        return await _get_order_or_404(order_id, db)

    @staticmethod
    async def confirm_inventory(
        order_id: int, data: InventoryConfirm, db: AsyncSession, actor: User
    ) -> Order:
        """Подтверждение менеджером (то же завершение с корректировкой остатков)."""
        return await WarehouseService.complete_inventory(order_id, data, db, actor)

    # ─── Stock view ───────────────────────────────────────────────────────────

    @staticmethod
    async def get_stocks(
        db: AsyncSession, product_id: Optional[int] = None
    ) -> list[Stock]:
        q = (
            select(Stock)
            .options(selectinload(Stock.product))
            .options(selectinload(Stock.cell))
            .where(Stock.quantity > 0)
            .order_by(Stock.product_id)
        )
        if product_id:
            q = q.where(Stock.product_id == product_id)
        result = await db.execute(q)
        return result.scalars().all()

    # ─── Stock management ─────────────────────────────────────────────────────

    @staticmethod
    async def clear_stocks(
        db: AsyncSession,
        actor: User,
        *,
        product_id: Optional[int] = None,
        cell_id: Optional[int] = None,
        cell_ids: Optional[list[int]] = None,
    ) -> dict:
        """
        "Удаление остатков" реализуем как обнуление quantity.
        Можно очистить:
        - по товару (product_id)
        - по ячейке (cell_id)
        - по списку ячеек (cell_ids) — нужно для bulk-операций по зоне/стеллажу
        """
        if product_id is None and cell_id is None and not cell_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нужно указать product_id или cell_id (или список cell_ids)",
            )

        q = (
            update(Stock)
            .where(Stock.quantity > 0)
            .values(quantity=0)
        )
        if product_id is not None:
            q = q.where(Stock.product_id == product_id)
        if cell_id is not None:
            q = q.where(Stock.cell_id == cell_id)
        if cell_ids:
            q = q.where(Stock.cell_id.in_(cell_ids))

        result = await db.execute(q)
        cleared_rows = result.rowcount or 0
        if cleared_rows == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Остатки не найдены по указанным фильтрам",
            )

        db.add(AuditLog(
            user_id=actor.id,
            action="CLEAR_STOCKS",
            entity="Stock",
            detail={
                "product_id": product_id,
                "cell_id": cell_id,
                "cell_ids_count": len(cell_ids) if cell_ids else 0,
                "rows": cleared_rows,
            },
        ))
        await db.commit()
        return {"cleared_rows": cleared_rows}

    # ─── Move stock between cells ─────────────────────────────────────────────

    @staticmethod
    async def move_stock(
        db: AsyncSession,
        actor: User,
        *,
        product_id: int,
        from_cell_id: int,
        to_cell_id: int,
        quantity: int,
    ) -> dict:
        if from_cell_id == to_cell_id:
            raise HTTPException(status_code=400, detail="from_cell_id и to_cell_id должны отличаться")

        product = await db.get(Product, product_id)
        if not product or not product.is_active:
            raise HTTPException(status_code=404, detail=f"Товар ID={product_id} не найден")

        from_cell = await db.get(StorageCell, from_cell_id)
        if not from_cell or not from_cell.is_active:
            raise HTTPException(status_code=404, detail="Ячейка-источник не найдена")

        to_cell = await db.get(StorageCell, to_cell_id)
        if not to_cell or not to_cell.is_active:
            raise HTTPException(status_code=404, detail="Ячейка-назначение не найдена")

        # Блокируем остаток источника
        res_from = await db.execute(
            select(Stock)
            .where(Stock.product_id == product_id, Stock.cell_id == from_cell_id)
            .with_for_update()
        )
        from_stock = res_from.scalar_one_or_none()
        available = from_stock.quantity if from_stock else 0
        if available < quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Недостаточно товара в ячейке {from_cell.address}. Доступно: {available} ед.",
            )

        # Блокируем все остатки в ячейке назначения и считаем занято
        res_to_all = await db.execute(
            select(Stock)
            .where(Stock.cell_id == to_cell_id)
            .with_for_update()
        )
        to_stocks = res_to_all.scalars().all()
        used = sum(int(s.quantity) for s in to_stocks)
        free = int(to_cell.max_capacity) - used
        if free < quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Недостаточно места в ячейке {to_cell.address}. Свободно: {free} ед.",
            )

        # Получаем/создаём остаток назначения (строка может уже быть в to_stocks)
        to_stock = None
        for s in to_stocks:
            if s.product_id == product_id:
                to_stock = s
                break
        if not to_stock:
            to_stock = Stock(product_id=product_id, cell_id=to_cell_id, quantity=0)
            db.add(to_stock)
            await db.flush()

        from_stock.quantity -= quantity
        to_stock.quantity += quantity

        db.add(AuditLog(
            user_id=actor.id,
            action="MOVE_STOCK",
            entity="Stock",
            detail={
                "product_id": product_id,
                "from_cell_id": from_cell_id,
                "to_cell_id": to_cell_id,
                "quantity": quantity,
            },
        ))
        await db.commit()
        return {
            "detail": "Перемещение выполнено",
            "product_id": product_id,
            "from_cell_id": from_cell_id,
            "to_cell_id": to_cell_id,
            "moved": quantity,
        }

    # ─── Orders list ──────────────────────────────────────────────────────────

    @staticmethod
    async def list_orders(
        db: AsyncSession,
        order_type: Optional[OrderType] = None,
        status: Optional[OrderStatus] = None,
        date_from: Optional["date"] = None,
        date_to: Optional["date"] = None,
        limit: int = 200,
    ) -> list[Order]:
        from datetime import date as date_type, datetime, time, timezone

        q = (
            select(Order)
            .options(selectinload(Order.items).selectinload(OrderItem.product))
            .options(selectinload(Order.items).selectinload(OrderItem.cell))
            .options(selectinload(Order.created_by_user))
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        if order_type:
            q = q.where(Order.type == order_type)
        if status:
            q = q.where(Order.status == status)
        if date_from:
            start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
            q = q.where(Order.created_at >= start)
        if date_to:
            end = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
            q = q.where(Order.created_at <= end)
        result = await db.execute(q)
        return result.scalars().all()

    # ─── Order deletion (safe cancel) ─────────────────────────────────────────

    @staticmethod
    async def delete_order(order_id: int, db: AsyncSession, actor: User) -> dict:
        """
        "Удаление" заказа реализуем как безопасную отмену:
        - ставим статус CANCELLED
        - для незавершённых заказов откатываем влияние на остатки

        Ограничения:
        - COMPLETED заказы не удаляем (история и факт операций)
        - INVENTORY, если уже COMPLETED (подтверждена) — не удаляем
        """
        order = await _get_order_or_404(order_id, db)
        prev_status = order.status

        if order.status == OrderStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Нельзя удалить завершённый заказ")

        # Загружаем позиции (на всякий случай, _get_order_or_404 уже подгружает)
        items = order.items or []

        # Откат остатков для активных операций
        if order.type == OrderType.ARRIVAL:
            # Заказы на приёмку (PENDING/IN_PROGRESS) остатки не меняют до complete_arrival.
            # Откат не требуется. Старые мгновенные приёмки были сразу COMPLETED — их не отменяем.
            pass

        elif order.type == OrderType.CONSUMPTION:
            # Расход при создании уменьшает остатки (резерв/списание) — при отмене возвращаем
            for it in items:
                if not it.cell_id:
                    continue
                st = await _get_or_create_stock(it.product_id, it.cell_id, db)
                st.quantity += int(it.quantity)

        elif order.type == OrderType.INVENTORY:
            for it in items:
                if it.quantity_fact is None:
                    continue
                delta = int(it.quantity_fact) - int(it.quantity)
                if delta == 0 or not it.cell_id:
                    continue
                st = await _get_or_create_stock(it.product_id, it.cell_id, db)
                st.quantity = max(0, int(st.quantity) - delta)
            inv_tasks = await db.execute(
                select(InventoryTask).where(InventoryTask.order_id == order.id)
            )
            for t in inv_tasks.scalars().all():
                if t.status != OrderStatus.CANCELLED:
                    t.status = OrderStatus.CANCELLED

        order.status = OrderStatus.CANCELLED
        order.closed_at = _now()

        db.add(AuditLog(
            user_id=actor.id,
            action="CANCEL_ORDER",
            entity="Order",
            entity_id=str(order_id),
            detail={"type": order.type.value, "prev_status": prev_status.value},
        ))
        await db.commit()
        return {"detail": "Заказ отменён", "order_id": order_id}

    @staticmethod
    async def delete_order_history(order_id: int, db: AsyncSession, actor: User) -> dict:
        """
        Физически удаляет запись из истории заказов.
        Разрешено только для завершённых/отменённых заказов, чтобы не ломать
        текущие активные процессы на складе.
        """
        order = await _get_order_or_404(order_id, db)
        if order.status not in (OrderStatus.COMPLETED, OrderStatus.CANCELLED):
            raise HTTPException(
                status_code=400,
                detail="Удалять из истории можно только завершённые или отменённые заказы",
            )

        await db.delete(order)
        db.add(AuditLog(
            user_id=actor.id,
            action="DELETE_ORDER_HISTORY",
            entity="Order",
            entity_id=str(order_id),
            detail={"status": order.status.value, "type": order.type.value},
        ))
        await db.commit()
        return {"detail": "Запись истории заказа удалена", "order_id": order_id}

    # ─── Move logs ────────────────────────────────────────────────────────────

    @staticmethod
    async def list_moves(db: AsyncSession, limit: int = 200) -> list[dict]:
        """
        Возвращает аудит перемещений (MOVE_STOCK) с обогащением:
        - username
        - product sku/name
        - from/to cell address
        """
        from sqlalchemy import desc

        q = (
            select(AuditLog)
            .options(selectinload(AuditLog.user))
            .where(AuditLog.action == "MOVE_STOCK")
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
        )
        res = await db.execute(q)
        logs = res.scalars().all()

        # Собираем ids для батч-загрузки
        product_ids: set[int] = set()
        cell_ids: set[int] = set()
        for log in logs:
            d = log.detail or {}
            pid = d.get("product_id")
            fc = d.get("from_cell_id")
            tc = d.get("to_cell_id")
            if isinstance(pid, int):
                product_ids.add(pid)
            if isinstance(fc, int):
                cell_ids.add(fc)
            if isinstance(tc, int):
                cell_ids.add(tc)

        products_by_id: dict[int, Product] = {}
        if product_ids:
            pres = await db.execute(select(Product).where(Product.id.in_(product_ids)))
            products_by_id = {p.id: p for p in pres.scalars().all()}

        cells_by_id: dict[int, StorageCell] = {}
        if cell_ids:
            cres = await db.execute(select(StorageCell).where(StorageCell.id.in_(cell_ids)))
            cells_by_id = {c.id: c for c in cres.scalars().all()}

        out: list[dict] = []
        for log in logs:
            d = log.detail or {}
            product_id = d.get("product_id")
            from_cell_id = d.get("from_cell_id")
            to_cell_id = d.get("to_cell_id")
            qty = d.get("quantity")

            p = products_by_id.get(product_id) if isinstance(product_id, int) else None
            fc = cells_by_id.get(from_cell_id) if isinstance(from_cell_id, int) else None
            tc = cells_by_id.get(to_cell_id) if isinstance(to_cell_id, int) else None

            out.append({
                "id": log.id,
                "created_at": log.created_at,
                "username": log.user.username if log.user else None,
                "product_id": product_id or 0,
                "product_sku": p.sku if p else None,
                "product_name": p.name if p else None,
                "from_cell_id": from_cell_id or 0,
                "from_cell_address": fc.address if fc else None,
                "to_cell_id": to_cell_id or 0,
                "to_cell_address": tc.address if tc else None,
                "quantity": int(qty or 0),
            })
        return out

    @staticmethod
    async def delete_move_log(move_log_id: int, db: AsyncSession, actor: User) -> dict:
        """
        Удаляет запись из истории перемещений (аудит MOVE_STOCK).
        Не меняет остатки, удаляется только запись журнала.
        """
        res = await db.execute(
            select(AuditLog).where(
                AuditLog.id == move_log_id,
                AuditLog.action == "MOVE_STOCK",
            )
        )
        log = res.scalar_one_or_none()
        if not log:
            raise HTTPException(status_code=404, detail="Запись перемещения не найдена")

        await db.execute(delete(AuditLog).where(AuditLog.id == move_log_id))
        db.add(AuditLog(
            user_id=actor.id,
            action="DELETE_MOVE_HISTORY",
            entity="AuditLog",
            entity_id=str(move_log_id),
            detail={"deleted_action": "MOVE_STOCK"},
        ))
        await db.commit()
        return {"detail": "Запись истории перемещения удалена", "move_log_id": move_log_id}
