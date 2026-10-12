from datetime import date
from typing import Annotated, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AnyAuthenticatedUser, CurrentUser, ManagerOrAbove
from app.db.database import get_db
from app.models.models import OrderStatus, OrderType, Stock
from app.schemas.bootstrap import WarehouseBootstrapRequest, WarehouseBootstrapResult
from app.schemas.warehouse import (
    ArrivalComplete, ArrivalCreate, ArrivalImportPayload, ConsumptionCreate,
    ConsumptionImportPayload, InventoryConfirm, InventoryCreate, OrderOut, RouteSheet,
    StockOut, StockMoveRequest, StockMoveResponse, MoveLogOut,
    InventoryTaskOut, InventoryLossSummaryOut,
)
from app.services.bootstrap_service import run_warehouse_bootstrap
from app.services.ml_service import run_training_task
from app.services.order_import import (
    parse_arrival_import_payload,
    parse_arrival_upload_file,
    parse_consumption_import_payload,
    parse_consumption_upload_file,
)
from app.services.warehouse_service import WarehouseService

router = APIRouter()


# ─── Stocks ───────────────────────────────────────────────────────────────────

@router.get("/stocks", response_model=List[StockOut], summary="Текущие остатки")
async def get_stocks(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
    product_id: Optional[int] = Query(None, description="Фильтр по товару"),
):
    return await WarehouseService.get_stocks(db, product_id)


@router.delete(
    "/stocks",
    summary="Удалить остатки (обнулить quantity)",
    dependencies=[ManagerOrAbove],
)
async def clear_stocks(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    product_id: Optional[int] = Query(None, description="Очистить остатки по товару"),
    cell_id: Optional[int] = Query(None, description="Очистить остатки по ячейке"),
):
    return await WarehouseService.clear_stocks(
        db=db,
        actor=current_user,
        product_id=product_id,
        cell_id=cell_id,
    )


@router.post(
    "/bootstrap",
    response_model=WarehouseBootstrapResult,
    summary="Согласованная загрузка склада (генератор)",
    dependencies=[ManagerOrAbove],
)
async def warehouse_bootstrap(
    payload: WarehouseBootstrapRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    """
    За один вызов: ячейки, каталог товаров, начальные остатки (завершённая приёмка),
    история спроса для ML. Данные должны быть согласованы (одни SKU и адреса ячеек).
    """
    result = await run_warehouse_bootstrap(payload, db, current_user)
    if payload.run_ml_training:
        background_tasks.add_task(run_training_task, None, True, None)
        result.ml_training_started = True
    return result


@router.post(
    "/move",
    response_model=StockMoveResponse,
    summary="Переместить товар между ячейками",
    dependencies=[AnyAuthenticatedUser],
)
async def move_stock(
    body: StockMoveRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await WarehouseService.move_stock(
        db=db,
        actor=current_user,
        product_id=body.product_id,
        from_cell_id=body.from_cell_id,
        to_cell_id=body.to_cell_id,
        quantity=body.quantity,
    )


# ─── Orders list ──────────────────────────────────────────────────────────────

@router.get("/orders", response_model=List[OrderOut], summary="Список заказов")
async def list_orders(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
    type: Optional[OrderType] = Query(None),
    status: Optional[OrderStatus] = Query(None),
    date_from: Optional[date] = Query(None, description="Начало периода (включительно)"),
    date_to: Optional[date] = Query(None, description="Конец периода (включительно)"),
    limit: int = Query(200, le=5000),
):
    orders = await WarehouseService.list_orders(
        db,
        order_type=type,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    result = []
    for order in orders:
        o = OrderOut(
            id=order.id,
            type=order.type,
            status=order.status,
            comment=order.comment,
            created_at=order.created_at,
            closed_at=order.closed_at,
            created_by=order.created_by_user.username if order.created_by_user else None,
            items=_map_items(order.items),
        )
        result.append(o)
    return result


@router.delete(
    "/orders/{order_id}",
    summary="Удалить (отменить) заказ",
    dependencies=[ManagerOrAbove],
)
async def delete_order(
    order_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await WarehouseService.delete_order(order_id, db, actor=current_user)


@router.delete(
    "/orders/{order_id}/history",
    summary="Удалить запись из истории заказов",
    dependencies=[ManagerOrAbove],
)
async def delete_order_history(
    order_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await WarehouseService.delete_order_history(order_id, db, actor=current_user)


@router.get(
    "/moves",
    response_model=List[MoveLogOut],
    summary="Список всех перемещений",
    dependencies=[ManagerOrAbove],
)
async def list_moves(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
    limit: int = Query(200, ge=1, le=1000),
):
    return await WarehouseService.list_moves(db, limit=limit)


@router.delete(
    "/moves/{move_log_id}",
    summary="Удалить запись из истории перемещений",
    dependencies=[ManagerOrAbove],
)
async def delete_move(
    move_log_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await WarehouseService.delete_move_log(move_log_id, db, actor=current_user)


@router.get("/orders/{order_id}", response_model=OrderOut, summary="Получить заказ")
async def get_order(
    order_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
):
    from app.services.warehouse_service import _get_order_or_404
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from app.models.models import Order, OrderItem
    order = await _get_order_or_404(order_id, db)
    return OrderOut(
        id=order.id,
        type=order.type,
        status=order.status,
        comment=order.comment,
        created_at=order.created_at,
        closed_at=order.closed_at,
        items=_map_items(order.items),
    )


# ─── Arrival ──────────────────────────────────────────────────────────────────

@router.post(
    "/arrival/requests",
    response_model=OrderOut,
    status_code=201,
    summary="Сформировать заказ на приёмку (для кладовщика)",
    dependencies=[ManagerOrAbove],
)
async def create_arrival_request(
    data: ArrivalCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order = await WarehouseService.create_arrival_request(data, db, actor=current_user)
    return _order_to_out(order)


@router.post(
    "/arrival/requests/import",
    response_model=OrderOut,
    status_code=201,
    summary="Сформировать заказ на приёмку из JSON",
    dependencies=[ManagerOrAbove],
)
async def import_arrival_request_json(
    payload: ArrivalImportPayload,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    data = await parse_arrival_import_payload(payload, db)
    order = await WarehouseService.create_arrival_request(data, db, actor=current_user)
    return _order_to_out(order)


@router.post(
    "/arrival/requests/upload",
    response_model=OrderOut,
    status_code=201,
    summary="Загрузить заказ на приёмку из Excel/CSV/JSON файла",
    dependencies=[ManagerOrAbove],
)
async def upload_arrival_request(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(..., description="Файл .xlsx, .xls, .csv или .json"),
    comment: Optional[str] = Form(None),
):
    data = await parse_arrival_upload_file(file, db, comment=comment)
    order = await WarehouseService.create_arrival_request(data, db, actor=current_user)
    return _order_to_out(order)


@router.post(
    "/arrival/{order_id}/start",
    response_model=OrderOut,
    summary="Взять заказ на приёмку в работу",
    dependencies=[AnyAuthenticatedUser],
)
async def start_arrival(
    order_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order = await WarehouseService.start_arrival(order_id, db, actor=current_user)
    return _order_to_out(order)


@router.post(
    "/arrival/{order_id}/complete",
    response_model=OrderOut,
    summary="Выполнить приёмку по заказу",
    dependencies=[AnyAuthenticatedUser],
)
async def complete_arrival(
    order_id: int,
    data: ArrivalComplete,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order = await WarehouseService.complete_arrival(order_id, data, db, actor=current_user)
    return _order_to_out(order)


# ─── Consumption ──────────────────────────────────────────────────────────────

@router.post(
    "/consumption/requests",
    response_model=OrderOut,
    status_code=201,
    summary="Сформировать заказ на расход (для кладовщика)",
    dependencies=[ManagerOrAbove],
)
async def create_consumption_request(
    data: ConsumptionCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Администратор/менеджер создаёт заказ в статусе PENDING.
    Остатки не списываются до тех пор, пока кладовщик не возьмёт заказ в работу.
    """
    order = await WarehouseService.create_consumption_request(data, db, actor=current_user)
    return _order_to_out(order)


@router.post(
    "/consumption/requests/import",
    response_model=OrderOut,
    status_code=201,
    summary="Сформировать заказ на расход из JSON",
    dependencies=[ManagerOrAbove],
)
async def import_consumption_request_json(
    payload: ConsumptionImportPayload,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    data = await parse_consumption_import_payload(payload, db)
    order = await WarehouseService.create_consumption_request(data, db, actor=current_user)
    return _order_to_out(order)


@router.post(
    "/consumption/requests/upload",
    response_model=OrderOut,
    status_code=201,
    summary="Загрузить заказ на расход из Excel/CSV/JSON файла",
    dependencies=[ManagerOrAbove],
)
async def upload_consumption_request(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(..., description="Файл .xlsx, .xls, .csv или .json"),
    comment: Optional[str] = Form(None),
):
    data = await parse_consumption_upload_file(file, db, comment=comment)
    order = await WarehouseService.create_consumption_request(data, db, actor=current_user)
    return _order_to_out(order)


@router.post(
    "/consumption/{order_id}/start",
    response_model=OrderOut,
    summary="Взять заказ на расход в работу",
    dependencies=[AnyAuthenticatedUser],
)
async def start_consumption(
    order_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order = await WarehouseService.start_consumption(order_id, db, actor=current_user)
    return _order_to_out(order)


@router.post(
    "/consumption/{order_id}/complete",
    response_model=OrderOut,
    summary="Завершить расход",
    dependencies=[AnyAuthenticatedUser],
)
async def complete_consumption(
    order_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order = await WarehouseService.complete_consumption(order_id, db, actor=current_user)
    return _order_to_out(order)


@router.get(
    "/consumption/{order_id}/route",
    response_model=RouteSheet,
    summary="Маршрутный лист",
)
async def get_route_sheet(
    order_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
):
    """Оптимальный порядок обхода ячеек для сборки заказа."""
    return await WarehouseService.get_route_sheet(order_id, db)


# ─── Inventory ────────────────────────────────────────────────────────────────

@router.post(
    "/inventory/requests",
    response_model=OrderOut,
    status_code=201,
    summary="Сформировать задание на инвентаризацию",
    dependencies=[ManagerOrAbove],
)
async def create_inventory_request(
    data: InventoryCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    product_ids = null → пересчёт всего склада (все позиции с остатком > 0).
    Кладовщик выполняет пересчёт в разделе «Инвентаризация».
    """
    order = await WarehouseService.create_inventory_request(data, db, actor=current_user)
    return _order_to_out(order)


@router.post(
    "/inventory",
    response_model=OrderOut,
    status_code=201,
    summary="Создать инвентаризацию (алиас)",
    dependencies=[ManagerOrAbove],
)
async def create_inventory(
    data: InventoryCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order = await WarehouseService.create_inventory_request(data, db, actor=current_user)
    return _order_to_out(order)


@router.get(
    "/inventory/{order_id}/tasks",
    response_model=List[InventoryTaskOut],
    summary="Подзадания инвентаризации (по стеллажам)",
)
async def list_inventory_tasks(
    order_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
):
    return await WarehouseService.list_inventory_tasks(order_id, db)


@router.post(
    "/inventory/{order_id}/tasks/{task_id}/start",
    response_model=InventoryTaskOut,
    summary="Взять стеллаж в работу",
    dependencies=[AnyAuthenticatedUser],
)
async def start_inventory_task(
    order_id: int,
    task_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await WarehouseService.start_inventory_task(order_id, task_id, db, actor=current_user)


@router.get(
    "/inventory/{order_id}/tasks/{task_id}/route",
    response_model=RouteSheet,
    summary="Маршрутный лист стеллажа",
)
async def get_inventory_task_route(
    order_id: int,
    task_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
):
    return await WarehouseService.get_inventory_task_route(order_id, task_id, db)


@router.post(
    "/inventory/{order_id}/tasks/{task_id}/complete",
    response_model=InventoryTaskOut,
    summary="Завершить пересчёт стеллажа",
    dependencies=[AnyAuthenticatedUser],
)
async def complete_inventory_task(
    order_id: int,
    task_id: int,
    data: InventoryConfirm,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await WarehouseService.complete_inventory_task(
        order_id, task_id, data, db, actor=current_user,
    )


@router.get(
    "/inventory/{order_id}/losses",
    response_model=InventoryLossSummaryOut,
    summary="Потери и излишки по инвентаризации",
)
async def get_inventory_losses(
    order_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
):
    return await WarehouseService.get_inventory_losses(order_id, db)


@router.post(
    "/inventory/{order_id}/start",
    response_model=OrderOut,
    summary="Взять инвентаризацию в работу (устар., см. подзадания)",
    dependencies=[AnyAuthenticatedUser],
)
async def start_inventory(
    order_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order = await WarehouseService.start_inventory(order_id, db, actor=current_user)
    return _order_to_out(order)


@router.get(
    "/inventory/{order_id}/route",
    response_model=RouteSheet,
    summary="Маршрутный лист инвентаризации",
)
async def get_inventory_route_sheet(
    order_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
):
    return await WarehouseService.get_route_sheet(order_id, db)


@router.post(
    "/inventory/{order_id}/complete",
    response_model=OrderOut,
    summary="Завершить инвентаризацию (фактические количества)",
    dependencies=[AnyAuthenticatedUser],
)
async def complete_inventory(
    order_id: int,
    data: InventoryConfirm,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order = await WarehouseService.complete_inventory(order_id, data, db, actor=current_user)
    return _order_to_out(order)


@router.post(
    "/inventory/{order_id}/confirm",
    response_model=OrderOut,
    summary="Подтвердить инвентаризацию (менеджер)",
    dependencies=[ManagerOrAbove],
)
async def confirm_inventory(
    order_id: int,
    data: InventoryConfirm,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    order = await WarehouseService.confirm_inventory(order_id, data, db, actor=current_user)
    return _order_to_out(order)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _map_items(items):
    from app.schemas.warehouse import OrderItemOut
    result = []
    for item in items:
        result.append(OrderItemOut(
            id=item.id,
            product_id=item.product_id,
            cell_id=item.cell_id,
            quantity=item.quantity,
            quantity_fact=item.quantity_fact,
            product_sku=item.product.sku if item.product else None,
            product_name=item.product.name if item.product else None,
            cell_address=item.cell.address if item.cell else None,
        ))
    return result


def _order_to_out(order) -> OrderOut:
    return OrderOut(
        id=order.id,
        type=order.type,
        status=order.status,
        comment=order.comment,
        created_at=order.created_at,
        closed_at=order.closed_at,
        created_by=order.created_by_user.username if order.created_by_user else None,
        items=_map_items(order.items),
    )
