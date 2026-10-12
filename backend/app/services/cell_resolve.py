"""Поиск ячеек по адресу или координатам (bootstrap, импорт заказов)."""

import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import StorageCell
from app.schemas.bootstrap import BootstrapOrderLine, BootstrapStockLine

CELL_ADDR_RE = re.compile(r"^([A-Z]{1,8})(\d+)-(\d+)-(\d+)$", re.IGNORECASE)

CellLine = BootstrapStockLine | BootstrapOrderLine


def parse_cell_address(addr: str) -> Optional[tuple[str, int, int, int]]:
    m = CELL_ADDR_RE.match((addr or "").strip())
    if not m:
        return None
    return m.group(1).upper(), int(m.group(2)), int(m.group(3)), int(m.group(4))


async def load_cells_maps(db: AsyncSession) -> tuple[dict[str, StorageCell], dict[tuple, StorageCell]]:
    cres = await db.execute(select(StorageCell))
    cells = list(cres.scalars().all())
    by_address: dict[str, StorageCell] = {}
    by_key: dict[tuple, StorageCell] = {}
    for cell in cells:
        by_address[cell.address.upper()] = cell
        by_key[(cell.zone.upper(), cell.rack, cell.shelf, cell.position)] = cell
    return by_address, by_key


def resolve_cell(
    line: CellLine,
    by_address: dict[str, StorageCell],
    by_key: dict[tuple, StorageCell],
) -> Optional[StorageCell]:
    if line.cell_zone and line.cell_rack and line.cell_shelf and line.cell_position:
        key = (
            line.cell_zone.strip().upper(),
            line.cell_rack,
            line.cell_shelf,
            line.cell_position,
        )
        cell = by_key.get(key)
        if cell:
            return cell

    addr_key = line.cell_address.strip().upper()
    cell = by_address.get(addr_key)
    if cell:
        return cell

    parsed = parse_cell_address(line.cell_address)
    if parsed:
        return by_key.get(parsed)
    return None
