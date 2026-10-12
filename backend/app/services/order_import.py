import json
from io import BytesIO
from typing import Any, Optional

import pandas as pd
from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Product, Stock, StorageCell
from app.schemas.warehouse import (
    ArrivalCreate,
    ArrivalImportPayload,
    ConsumptionCreate,
    ConsumptionImportPayload,
    OrderItemCreate,
)


SKU_ALIASES = {"sku", "артикул", "код", "product_sku", "товар"}
QTY_ALIASES = {"quantity", "qty", "количество", "кол-во", "колво", "amount"}
CELL_ALIASES = {"cell", "cell_address", "ячейка", "адрес", "address", "cell_id"}


def _norm_col(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_")


def _pick_column(columns: list[str], aliases: set[str]) -> Optional[str]:
    for col in columns:
        if _norm_col(col) in aliases:
            return col
    return None


def _parse_quantity(value: Any) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("пустое количество")
    try:
        qty = int(float(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"некорректное количество: {value}") from exc
    if qty <= 0:
        raise ValueError("количество должно быть больше 0")
    return qty


def _rows_from_dataframe(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        raise HTTPException(status_code=400, detail="Файл не содержит данных")

    sku_col = _pick_column(list(df.columns), SKU_ALIASES)
    qty_col = _pick_column(list(df.columns), QTY_ALIASES)
    cell_col = _pick_column(list(df.columns), CELL_ALIASES)

    if not sku_col or not qty_col:
        raise HTTPException(
            status_code=400,
            detail="В файле нужны колонки SKU (артикул) и quantity (количество)",
        )

    rows: list[dict] = []
    for idx, row in df.iterrows():
        sku = str(row[sku_col]).strip()
        if not sku or sku.lower() == "nan":
            continue
        try:
            qty = _parse_quantity(row[qty_col])
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Строка {int(idx) + 2}: {exc}",
            ) from exc

        cell_address = None
        if cell_col is not None and not pd.isna(row.get(cell_col)):
            cell_address = str(row[cell_col]).strip()
            if cell_address.lower() == "nan":
                cell_address = None

        rows.append({"sku": sku, "quantity": qty, "cell_address": cell_address})
    return rows


def parse_excel_bytes(content: bytes, filename: str) -> list[dict]:
    try:
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(BytesIO(content))
        else:
            df = pd.read_excel(BytesIO(content))
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Не удалось прочитать файл: {exc}",
        ) from exc
    return _rows_from_dataframe(df)


def parse_json_bytes(content: bytes) -> list[dict]:
    try:
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Некорректный JSON") from exc

    if isinstance(data, dict):
        items = data.get("items", [])
        if not isinstance(items, list):
            raise HTTPException(status_code=400, detail="Поле items должно быть массивом")
    elif isinstance(data, list):
        items = data
    else:
        raise HTTPException(status_code=400, detail="JSON должен быть объектом или массивом позиций")

    rows: list[dict] = []
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail=f"Позиция {i}: ожидается объект")
        sku = str(item.get("sku") or item.get("product_sku") or "").strip()
        if not sku:
            raise HTTPException(status_code=400, detail=f"Позиция {i}: не указан sku")
        try:
            qty = _parse_quantity(item.get("quantity") or item.get("qty"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Позиция {i}: {exc}") from exc
        cell_address = item.get("cell_address") or item.get("cell") or item.get("ячейка")
        if cell_address is not None:
            cell_address = str(cell_address).strip() or None
        rows.append({"sku": sku, "quantity": qty, "cell_address": cell_address})
    return rows


async def _load_products_by_sku(rows: list[dict], db: AsyncSession) -> dict[str, Product]:
    skus = {r["sku"].upper() for r in rows}
    pres = await db.execute(select(Product).where(func.upper(Product.sku).in_(skus)))
    return {p.sku.upper(): p for p in pres.scalars().all()}


async def _get_available_stock(product_id: int, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(Stock.quantity), 0)).where(
            Stock.product_id == product_id,
            Stock.quantity > 0,
        )
    )
    return int(result.scalar_one())


async def _parse_file_content(
    file: UploadFile,
    *,
    comment: Optional[str] = None,
) -> tuple[list[dict], Optional[str]]:
    filename = (file.filename or "").lower()
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пуст")

    if filename.endswith(".json"):
        rows = parse_json_bytes(content)
    elif filename.endswith((".xlsx", ".xls", ".csv")):
        rows = parse_excel_bytes(content, filename)
    else:
        raise HTTPException(
            status_code=400,
            detail="Поддерживаются файлы: .xlsx, .xls, .csv, .json",
        )
    return rows, comment


async def resolve_arrival_rows(
    rows: list[dict],
    db: AsyncSession,
    *,
    comment: Optional[str] = None,
) -> ArrivalCreate:
    if not rows:
        raise HTTPException(status_code=400, detail="Нет позиций для импорта")

    products = await _load_products_by_sku(rows, db)
    cres = await db.execute(select(StorageCell).where(StorageCell.is_active.is_(True)))
    cells_by_address = {c.address.upper(): c for c in cres.scalars().all()}

    items: list[OrderItemCreate] = []
    for i, row in enumerate(rows, start=1):
        sku_key = row["sku"].upper()
        product = products.get(sku_key)
        if not product or not product.is_active:
            raise HTTPException(
                status_code=400,
                detail=f"Строка {i}: товар с SKU «{row['sku']}» не найден",
            )

        cell_id = None
        if row.get("cell_address"):
            cell = cells_by_address.get(str(row["cell_address"]).upper())
            if not cell:
                raise HTTPException(
                    status_code=400,
                    detail=f"Строка {i}: ячейка «{row['cell_address']}» не найдена",
                )
            cell_id = cell.id

        items.append(OrderItemCreate(
            product_id=product.id,
            quantity=row["quantity"],
            cell_id=cell_id,
        ))

    return ArrivalCreate(comment=comment, items=items)


async def resolve_consumption_rows(
    rows: list[dict],
    db: AsyncSession,
    *,
    comment: Optional[str] = None,
) -> ConsumptionCreate:
    if not rows:
        raise HTTPException(status_code=400, detail="Нет позиций для импорта")

    products = await _load_products_by_sku(rows, db)
    items: list[OrderItemCreate] = []

    for i, row in enumerate(rows, start=1):
        sku_key = row["sku"].upper()
        product = products.get(sku_key)
        if not product or not product.is_active:
            raise HTTPException(
                status_code=400,
                detail=f"Строка {i}: товар с SKU «{row['sku']}» не найден",
            )

        available = await _get_available_stock(product.id, db)
        if available < row["quantity"]:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Строка {i}: недостаточно товара «{product.sku}» на складе. "
                    f"Доступно: {available} ед., запрошено: {row['quantity']} ед."
                ),
            )

        items.append(OrderItemCreate(
            product_id=product.id,
            quantity=row["quantity"],
        ))

    return ConsumptionCreate(comment=comment, items=items)


async def parse_arrival_upload_file(
    file: UploadFile,
    db: AsyncSession,
    *,
    comment: Optional[str] = None,
) -> ArrivalCreate:
    rows, comment = await _parse_file_content(file, comment=comment)
    return await resolve_arrival_rows(rows, db, comment=comment)


async def parse_arrival_import_payload(
    payload: ArrivalImportPayload,
    db: AsyncSession,
) -> ArrivalCreate:
    rows = [
        {"sku": item.sku, "quantity": item.quantity, "cell_address": item.cell_address}
        for item in payload.items
    ]
    return await resolve_arrival_rows(rows, db, comment=payload.comment)


async def parse_consumption_upload_file(
    file: UploadFile,
    db: AsyncSession,
    *,
    comment: Optional[str] = None,
) -> ConsumptionCreate:
    rows, comment = await _parse_file_content(file, comment=comment)
    return await resolve_consumption_rows(rows, db, comment=comment)


async def parse_consumption_import_payload(
    payload: ConsumptionImportPayload,
    db: AsyncSession,
) -> ConsumptionCreate:
    rows = [
        {"sku": item.sku, "quantity": item.quantity, "cell_address": item.cell_address}
        for item in payload.items
    ]
    return await resolve_consumption_rows(rows, db, comment=payload.comment)
