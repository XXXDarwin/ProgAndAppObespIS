from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AdminOnly, AnyAuthenticatedUser, CurrentUser, ManagerOrAbove
from app.db.database import get_db
from app.models.models import AuditLog, Stock, StorageCell
from app.schemas.warehouse import CellBulkCreate, CellCreate, CellOut, CellWithStock

router = APIRouter()


@router.get("/", response_model=List[CellWithStock], summary="Список ячеек")
async def list_cells(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
):
    # Загружаем ячейки с суммой остатков
    load_sq = (
        select(Stock.cell_id, func.sum(Stock.quantity).label("total"))
        .group_by(Stock.cell_id)
        .subquery()
    )
    result = await db.execute(
        select(StorageCell, func.coalesce(load_sq.c.total, 0).label("used"))
        .outerjoin(load_sq, load_sq.c.cell_id == StorageCell.id)
        .where(StorageCell.is_active.is_(True))
        .order_by(StorageCell.zone, StorageCell.rack, StorageCell.shelf, StorageCell.position)
    )
    rows = result.all()
    out = []
    for cell, used in rows:
        d = {
            "id": cell.id,
            "zone": cell.zone,
            "rack": cell.rack,
            "shelf": cell.shelf,
            "position": cell.position,
            "max_capacity": cell.max_capacity,
            "is_active": cell.is_active,
            "address": cell.address,
            "current_stock": int(used),
            "free_capacity": cell.max_capacity - int(used),
        }
        out.append(d)
    return out


@router.post(
    "/",
    response_model=CellOut,
    status_code=201,
    summary="Создать одну ячейку",
    dependencies=[AdminOnly],
)
async def create_cell(
    data: CellCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    cell = StorageCell(**data.model_dump())
    db.add(cell)
    db.add(AuditLog(
        user_id=current_user.id,
        action="CREATE_CELL",
        entity="StorageCell",
        detail=data.model_dump(),
    ))
    await db.commit()
    await db.refresh(cell)
    return cell


@router.post(
    "/bulk",
    summary="Массовое создание ячеек",
    dependencies=[AdminOnly],
)
async def bulk_create_cells(
    data: CellBulkCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Генерирует ячейки по схеме:
    зоны × стеллажи × полки × позиции
    """
    created = 0
    skipped = 0
    for zone in data.zones:
        zone = zone.strip().upper()
        for rack in range(1, data.racks_per_zone + 1):
            for shelf in range(1, data.shelves_per_rack + 1):
                for pos in range(1, data.positions_per_shelf + 1):
                    # Пропускаем дубликаты
                    exists = await db.execute(
                        select(StorageCell).where(
                            StorageCell.zone == zone,
                            StorageCell.rack == rack,
                            StorageCell.shelf == shelf,
                            StorageCell.position == pos,
                        )
                    )
                    existing = exists.scalar_one_or_none()
                    if existing:
                        skipped += 1
                        if not existing.is_active:
                            existing.is_active = True
                        continue
                    db.add(StorageCell(
                        zone=zone, rack=rack, shelf=shelf,
                        position=pos, max_capacity=data.max_capacity,
                    ))
                    created += 1

    db.add(AuditLog(
        user_id=current_user.id,
        action="BULK_CREATE_CELLS",
        entity="StorageCell",
        detail={"created": created, "skipped": skipped},
    ))
    await db.commit()
    return {"created": created, "skipped": skipped}


@router.delete(
    "/{cell_id}",
    summary="Деактивировать ячейку",
    dependencies=[AdminOnly],
)
async def deactivate_cell(
    cell_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(StorageCell).where(StorageCell.id == cell_id))
    cell = result.scalar_one_or_none()
    if not cell:
        raise HTTPException(status_code=404, detail="Ячейка не найдена")

    # Проверяем что ячейка пуста
    stock_result = await db.execute(
        select(func.sum(Stock.quantity)).where(Stock.cell_id == cell_id)
    )
    total = stock_result.scalar() or 0
    if total > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Нельзя деактивировать: в ячейке есть товары ({total} ед.)",
        )

    cell.is_active = False
    db.add(AuditLog(
        user_id=current_user.id,
        action="DEACTIVATE_CELL",
        entity="StorageCell",
        entity_id=str(cell_id),
    ))
    await db.commit()
    return {"detail": "Ячейка деактивирована"}


@router.delete(
    "/zone/{zone}/rack/{rack}",
    summary="Удалить (деактивировать) стеллаж целиком: все ячейки в зоне/стеллаже",
    dependencies=[AdminOnly],
)
async def deactivate_rack(
    zone: str,
    rack: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    force_clear_stock: bool = False,
):
    """
    Массово деактивирует все активные ячейки в заданной зоне/стеллаже.

    По умолчанию (force_clear_stock=false) операция запрещена, если в любой ячейке есть остатки.
    Если force_clear_stock=true — сначала обнуляет остатки во всех ячейках стеллажа, затем деактивирует.
    """
    z = zone.strip().upper()
    result = await db.execute(
        select(StorageCell).where(
            StorageCell.zone == z,
            StorageCell.rack == rack,
            StorageCell.is_active.is_(True),
        )
    )
    cells = result.scalars().all()
    if not cells:
        raise HTTPException(status_code=404, detail="Ячейки в указанной зоне/стеллаже не найдены")

    cell_ids = [c.id for c in cells]

    stock_result = await db.execute(
        select(func.coalesce(func.sum(Stock.quantity), 0)).where(Stock.cell_id.in_(cell_ids))
    )
    total = stock_result.scalar() or 0
    if total > 0 and not force_clear_stock:
        raise HTTPException(
            status_code=400,
            detail=f"Нельзя удалить стеллаж: в ячейках есть товары ({total} ед.). "
                   f"Очистите остатки или используйте force_clear_stock=true",
        )

    cleared_rows = 0
    if force_clear_stock and total > 0:
        from app.services.warehouse_service import WarehouseService
        res = await WarehouseService.clear_stocks(db=db, actor=current_user, cell_ids=cell_ids)
        cleared_rows = int(res.get("cleared_rows") or 0)

    for c in cells:
        c.is_active = False

    db.add(AuditLog(
        user_id=current_user.id,
        action="BULK_DEACTIVATE_CELLS",
        entity="StorageCell",
        detail={
            "zone": z,
            "rack": rack,
            "cells": len(cell_ids),
            "force_clear_stock": force_clear_stock,
            "cleared_stock_rows": cleared_rows,
        },
    ))
    await db.commit()
    return {
        "detail": "Стеллаж деактивирован",
        "zone": z,
        "rack": rack,
        "cells_deactivated": len(cell_ids),
        "cleared_stock_rows": cleared_rows,
    }
