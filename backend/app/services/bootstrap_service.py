"""
Согласованная загрузка склада: ячейки → товары → остатки (приёмка) → история спроса.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Product, StorageCell, User
from app.schemas.bootstrap import (
    BootstrapStockLine,
    WarehouseBootstrapRequest,
    WarehouseBootstrapResult,
)
from app.schemas.products import ProductCreate
from app.schemas.warehouse import ArrivalComplete, ArrivalCompleteItem, ArrivalCreate, CellBulkCreate, OrderItemCreate
from app.services.cell_resolve import load_cells_maps, resolve_cell
from app.services.history_import_service import import_demand_history
from app.services.product_import import _get_or_create_category
from app.services.product_service import ProductService
from app.services.warehouse_service import WarehouseService


async def _bulk_create_cells(data: CellBulkCreate, db: AsyncSession, actor: User) -> tuple[int, int, int]:
    from app.models.models import AuditLog

    created = 0
    skipped = 0
    reactivated = 0
    for zone in data.zones:
        zone = zone.strip().upper()
        for rack in range(1, data.racks_per_zone + 1):
            for shelf in range(1, data.shelves_per_rack + 1):
                for pos in range(1, data.positions_per_shelf + 1):
                    exists = await db.execute(
                        select(StorageCell).where(
                            StorageCell.zone == zone,
                            StorageCell.rack == rack,
                            StorageCell.shelf == shelf,
                            StorageCell.position == pos,
                        )
                    )
                    cell = exists.scalar_one_or_none()
                    if cell:
                        skipped += 1
                        if not cell.is_active:
                            cell.is_active = True
                            reactivated += 1
                        if cell.max_capacity < data.max_capacity:
                            cell.max_capacity = data.max_capacity
                        continue
                    db.add(StorageCell(
                        zone=zone,
                        rack=rack,
                        shelf=shelf,
                        position=pos,
                        max_capacity=data.max_capacity,
                    ))
                    created += 1

    if created or reactivated:
        db.add(AuditLog(
            user_id=actor.id,
            action="BULK_CREATE_CELLS",
            entity="StorageCell",
            detail={"created": created, "skipped": skipped, "reactivated": reactivated},
        ))
        await db.commit()
    return created, skipped, reactivated


async def _import_products(
    request: WarehouseBootstrapRequest,
    db: AsyncSession,
    actor: User,
) -> tuple[int, int, list[str]]:
    if not request.products:
        return 0, 0, []

    items: list[ProductCreate] = []
    for row in request.products:
        category_id = None
        if row.category:
            category_id = await _get_or_create_category(row.category, db)
        items.append(ProductCreate(
            sku=row.sku,
            name=row.name,
            unit=row.unit or "шт",
            category_id=category_id,
            weight=row.weight,
            description=row.description,
        ))

    result = await ProductService.bulk_import_products(
        items,
        db,
        actor=actor,
        skip_duplicates=request.skip_existing_products,
    )
    return result.created, result.skipped, result.errors


async def _apply_initial_stock(
    lines: list[BootstrapStockLine],
    db: AsyncSession,
    actor: User,
    comment: str,
    *,
    arrival_chunk_size: int = 25,
) -> tuple[int, int, list[str]]:
    if not lines:
        return 0, 0, []

    warnings: list[str] = []
    pres = await db.execute(select(Product))
    products_by_sku = {p.sku.upper(): p for p in pres.scalars().all()}

    by_address, by_key = await load_cells_maps(db)

    order_items: list[OrderItemCreate] = []
    applied = 0
    reactivated_any = False

    for i, line in enumerate(lines, start=1):
        sku_key = line.sku.upper()
        product = products_by_sku.get(sku_key)
        if not product:
            warnings.append(f"Остаток строка {i}: SKU «{line.sku}» не найден")
            continue
        cell = resolve_cell(line, by_address, by_key)
        if not cell:
            warnings.append(f"Остаток строка {i}: ячейка «{line.cell_address}» не найдена")
            continue
        if not cell.is_active:
            cell.is_active = True
            reactivated_any = True
        order_items.append(OrderItemCreate(
            product_id=product.id,
            quantity=line.quantity,
            cell_id=cell.id,
        ))
        applied += 1

    if reactivated_any:
        await db.commit()

    if not order_items:
        return 0, 0, warnings

    orders_done = 0
    for offset in range(0, len(order_items), arrival_chunk_size):
        chunk = order_items[offset: offset + arrival_chunk_size]
        data = ArrivalCreate(
            comment=f"{comment} (начальные остатки {offset // arrival_chunk_size + 1})",
            items=chunk,
        )
        order = await WarehouseService.create_arrival_request(data, db, actor=actor)
        order = await WarehouseService.start_arrival(order.id, db, actor=actor)
        complete_items = [
            ArrivalCompleteItem(
                order_item_id=item.id,
                quantity=item.quantity,
                cell_id=item.cell_id,
            )
            for item in order.items
        ]
        await WarehouseService.complete_arrival(
            order.id,
            ArrivalComplete(items=complete_items),
            db,
            actor=actor,
        )
        orders_done += 1

    return applied, orders_done, warnings


async def run_warehouse_bootstrap(
    request: WarehouseBootstrapRequest,
    db: AsyncSession,
    actor: User,
) -> WarehouseBootstrapResult:
    result = WarehouseBootstrapResult()
    all_warnings: list[str] = []

    if request.cells:
        created, skipped, reactivated = await _bulk_create_cells(request.cells, db, actor)
        result.cells_created = created
        result.cells_skipped = skipped
        result.cells_reactivated = reactivated

    if request.products:
        created, skipped, errs = await _import_products(request, db, actor)
        result.products_created = created
        result.products_skipped = skipped
        all_warnings.extend(errs)

    if request.timed_orders:
        from app.services.timed_orders_import_service import import_timed_orders

        timed = await import_timed_orders(request.timed_orders, db, actor)
        result.timed_arrivals = timed.arrivals
        result.timed_consumptions = timed.consumptions
        result.timed_inventories = timed.inventories
        result.timed_moves = timed.moves
        result.timed_inventory_items = timed.inventory_items
        result.arrival_orders_completed = timed.arrivals
        result.history_orders = timed.consumptions
        result.history_items = timed.consumption_items
        result.stock_lines_applied = timed.arrival_items
        all_warnings.extend(timed.warnings)
    elif request.initial_stock:
        applied, orders, warns = await _apply_initial_stock(
            request.initial_stock,
            db,
            actor,
            request.comment or "Bootstrap",
        )
        result.stock_lines_applied = applied
        result.arrival_orders_completed = orders
        all_warnings.extend(warns)

    if request.demand_history and request.demand_history.records and not request.timed_orders:
        hist = await import_demand_history(request.demand_history, db, actor)
        result.history_orders = hist.orders_created
        result.history_items = hist.items_created

    result.warnings = all_warnings[:50]
    if len(all_warnings) > 50:
        result.warnings.append(f"…и ещё {len(all_warnings) - 50} предупреждений")
    return result
