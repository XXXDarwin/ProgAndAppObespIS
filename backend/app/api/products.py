from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, ManagerOrAbove, AnyAuthenticatedUser
from app.db.database import get_db
from app.schemas.products import (
    CategoryCreate, CategoryOut, ProductCreate, ProductImportPayload,
    ProductImportResult, ProductOut, ProductUpdate,
)
from app.services.product_import import parse_import_payload, parse_upload_file
from app.services.product_service import ProductService

router = APIRouter()


# ─── Categories ───────────────────────────────────────────────────────────────

@router.get("/categories", response_model=List[CategoryOut], summary="Список категорий")
async def list_categories(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
):
    return await ProductService.get_categories(db)


@router.post(
    "/categories",
    response_model=CategoryOut,
    status_code=201,
    summary="Создать категорию",
    dependencies=[ManagerOrAbove],
)
async def create_category(
    data: CategoryCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ProductService.create_category(data, db)


# ─── Products ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[ProductOut], summary="Список товаров")
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
    category_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None, description="Поиск по SKU или названию"),
    active_only: bool = Query(True),
):
    return await ProductService.list_products(db, category_id, search, active_only)


@router.get("/{product_id}", response_model=ProductOut, summary="Получить товар")
async def get_product(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
):
    return await ProductService.get_product(product_id, db)


@router.get("/by-sku/{sku}", response_model=ProductOut, summary="Найти по SKU")
async def get_by_sku(
    sku: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, AnyAuthenticatedUser],
):
    from fastapi import HTTPException
    p = await ProductService.get_by_sku(sku, db)
    if not p:
        raise HTTPException(status_code=404, detail=f"Товар с SKU '{sku}' не найден")
    return p


@router.post(
    "/",
    response_model=ProductOut,
    status_code=201,
    summary="Создать товар",
    dependencies=[ManagerOrAbove],
)
async def create_product(
    data: ProductCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ProductService.create_product(data, db, actor=current_user)


@router.post(
    "/import",
    response_model=ProductImportResult,
    summary="Импорт списка товаров из JSON",
    dependencies=[ManagerOrAbove],
)
async def import_products_json(
    payload: ProductImportPayload,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    items = await parse_import_payload(payload, db)
    return await ProductService.bulk_import_products(
        items, db, actor=current_user, skip_duplicates=payload.skip_duplicates,
    )


@router.post(
    "/upload",
    response_model=ProductImportResult,
    summary="Загрузить список товаров из Excel/CSV/JSON файла",
    dependencies=[ManagerOrAbove],
)
async def upload_products(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(..., description="Файл .xlsx, .xls, .csv или .json"),
    skip_duplicates: bool = Query(True, description="Пропускать существующие SKU"),
):
    items = await parse_upload_file(file, db)
    return await ProductService.bulk_import_products(
        items, db, actor=current_user, skip_duplicates=skip_duplicates,
    )


@router.patch(
    "/{product_id}",
    response_model=ProductOut,
    summary="Обновить товар",
    dependencies=[ManagerOrAbove],
)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ProductService.update_product(product_id, data, db, actor=current_user)


@router.delete(
    "/{product_id}",
    summary="Удалить (деактивировать) товар",
    dependencies=[ManagerOrAbove],
)
async def delete_product(
    product_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await ProductService.deactivate_product(product_id, db, actor=current_user)
