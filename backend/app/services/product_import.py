import json
from io import BytesIO
from typing import Any, Optional

import pandas as pd
from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Category, Product
from app.schemas.products import ProductCreate, ProductImportPayload


SKU_ALIASES = {"sku", "артикул", "код", "product_sku"}
NAME_ALIASES = {"name", "название", "наименование", "товар", "product_name"}
UNIT_ALIASES = {"unit", "ед", "единица", "ед_изм"}
CATEGORY_ALIASES = {"category", "category_name", "категория", "группа"}
WEIGHT_ALIASES = {"weight", "вес", "масса", "кг"}
DESC_ALIASES = {"description", "описание", "comment", "комментарий"}


def _norm_col(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_")


def _pick_column(columns: list[str], aliases: set[str]) -> Optional[str]:
    for col in columns:
        if _norm_col(col) in aliases:
            return col
    return None


def _cell_str(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return s if s and s.lower() != "nan" else None


def _parse_weight(value: Any) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        w = float(value)
        return w if w > 0 else None
    except (TypeError, ValueError):
        return None


def _rows_from_dataframe(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        raise HTTPException(status_code=400, detail="Файл не содержит данных")

    sku_col = _pick_column(list(df.columns), SKU_ALIASES)
    name_col = _pick_column(list(df.columns), NAME_ALIASES)
    unit_col = _pick_column(list(df.columns), UNIT_ALIASES)
    cat_col = _pick_column(list(df.columns), CATEGORY_ALIASES)
    weight_col = _pick_column(list(df.columns), WEIGHT_ALIASES)
    desc_col = _pick_column(list(df.columns), DESC_ALIASES)

    if not sku_col or not name_col:
        raise HTTPException(
            status_code=400,
            detail="В файле нужны колонки SKU (артикул) и name (название)",
        )

    rows: list[dict] = []
    for idx, row in df.iterrows():
        sku = _cell_str(row[sku_col])
        name = _cell_str(row[name_col])
        if not sku or not name:
            continue
        rows.append({
            "sku": sku,
            "name": name,
            "unit": _cell_str(row[unit_col]) if unit_col else None,
            "category": _cell_str(row[cat_col]) if cat_col else None,
            "weight": _parse_weight(row[weight_col]) if weight_col else None,
            "description": _cell_str(row[desc_col]) if desc_col else None,
        })
    return rows


def parse_excel_bytes(content: bytes, filename: str) -> list[dict]:
    try:
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(BytesIO(content))
        else:
            df = pd.read_excel(BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось прочитать файл: {exc}") from exc
    return _rows_from_dataframe(df)


def parse_json_bytes(content: bytes) -> list[dict]:
    try:
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Некорректный JSON") from exc

    if isinstance(data, dict):
        items = data.get("items", data.get("products", []))
        if not isinstance(items, list):
            raise HTTPException(status_code=400, detail="Поле items должно быть массивом")
    elif isinstance(data, list):
        items = data
    else:
        raise HTTPException(status_code=400, detail="JSON должен быть объектом или массивом товаров")

    rows: list[dict] = []
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail=f"Позиция {i}: ожидается объект")
        sku = _cell_str(item.get("sku") or item.get("product_sku"))
        name = _cell_str(item.get("name") or item.get("product_name") or item.get("название"))
        if not sku:
            raise HTTPException(status_code=400, detail=f"Позиция {i}: не указан sku")
        if not name:
            raise HTTPException(status_code=400, detail=f"Позиция {i}: не указано название")
        rows.append({
            "sku": sku,
            "name": name,
            "unit": _cell_str(item.get("unit") or item.get("единица")),
            "category": _cell_str(item.get("category") or item.get("category_name") or item.get("категория")),
            "weight": _parse_weight(item.get("weight") or item.get("вес")),
            "description": _cell_str(item.get("description") or item.get("описание")),
        })
    return rows


async def _get_or_create_category(name: str, db: AsyncSession) -> int:
    result = await db.execute(select(Category).where(Category.name == name))
    cat = result.scalar_one_or_none()
    if cat:
        return cat.id
    cat = Category(name=name)
    db.add(cat)
    await db.flush()
    return cat.id


async def rows_to_product_creates(rows: list[dict], db: AsyncSession) -> list[ProductCreate]:
    if not rows:
        raise HTTPException(status_code=400, detail="Нет товаров для импорта")

    items: list[ProductCreate] = []
    for i, row in enumerate(rows, start=1):
        sku = row["sku"].strip().upper()
        if not sku:
            raise HTTPException(status_code=400, detail=f"Строка {i}: пустой SKU")

        category_id = None
        if row.get("category"):
            category_id = await _get_or_create_category(row["category"], db)

        items.append(ProductCreate(
            sku=sku,
            name=row["name"].strip(),
            unit=row.get("unit") or "шт",
            category_id=category_id,
            weight=row.get("weight"),
            description=row.get("description"),
        ))
    return items


async def parse_upload_file(file: UploadFile, db: AsyncSession) -> list[ProductCreate]:
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
    return await rows_to_product_creates(rows, db)


async def parse_import_payload(payload: ProductImportPayload, db: AsyncSession) -> list[ProductCreate]:
    rows = [
        {
            "sku": item.sku,
            "name": item.name,
            "unit": item.unit,
            "category": item.category,
            "weight": item.weight,
            "description": item.description,
        }
        for item in payload.items
    ]
    return await rows_to_product_creates(rows, db)
