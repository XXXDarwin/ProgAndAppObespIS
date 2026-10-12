from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import AuditLog, Category, Product, Stock, User
from app.schemas.products import CategoryCreate, ProductCreate, ProductImportResult, ProductUpdate


class ProductService:

    # ─── Categories ───────────────────────────────────────────────────────────

    @staticmethod
    async def get_categories(db: AsyncSession) -> list[Category]:
        result = await db.execute(select(Category).order_by(Category.name))
        return result.scalars().all()

    @staticmethod
    async def create_category(data: CategoryCreate, db: AsyncSession) -> Category:
        existing = await db.execute(select(Category).where(Category.name == data.name))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"Категория '{data.name}' уже существует")
        cat = Category(name=data.name)
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        return cat

    # ─── Products ─────────────────────────────────────────────────────────────

    @staticmethod
    async def list_products(
        db: AsyncSession,
        category_id: Optional[int] = None,
        search: Optional[str] = None,
        active_only: bool = True,
    ) -> list[dict]:
        # Загружаем товары с суммой остатков
        q = (
            select(
                Product,
                func.coalesce(func.sum(Stock.quantity), 0).label("total_stock"),
            )
            .outerjoin(Stock, Stock.product_id == Product.id)
            .options(selectinload(Product.category))
            .group_by(Product.id)
            .order_by(Product.sku)
        )
        if active_only:
            q = q.where(Product.is_active.is_(True))
        if category_id:
            q = q.where(Product.category_id == category_id)
        if search:
            term = f"%{search.lower()}%"
            q = q.where(
                (func.lower(Product.sku).like(term)) |
                (func.lower(Product.name).like(term))
            )

        rows = await db.execute(q)
        result = []
        for product, total_stock in rows.all():
            d = product.__dict__.copy()
            d["total_stock"] = total_stock
            d["category"] = product.category
            result.append(d)
        return result

    @staticmethod
    async def get_product(product_id: int, db: AsyncSession) -> Product:
        result = await db.execute(
            select(Product)
            .options(selectinload(Product.category))
            .where(Product.id == product_id)
        )
        p = result.scalar_one_or_none()
        if not p:
            raise HTTPException(status_code=404, detail="Товар не найден")
        return p

    @staticmethod
    async def get_by_sku(sku: str, db: AsyncSession) -> Optional[Product]:
        result = await db.execute(select(Product).where(Product.sku == sku.upper()))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_product(
        data: ProductCreate, db: AsyncSession, actor: User
    ) -> Product:
        existing = await db.execute(select(Product).where(Product.sku == data.sku))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"Товар со SKU '{data.sku}' уже существует")

        product = Product(**data.model_dump())
        db.add(product)
        await db.flush()

        db.add(AuditLog(
            user_id=actor.id,
            action="CREATE_PRODUCT",
            entity="Product",
            entity_id=str(product.id),
            detail={"sku": product.sku, "name": product.name},
        ))
        await db.commit()
        await db.refresh(product)
        return product

    @staticmethod
    async def update_product(
        product_id: int, data: ProductUpdate, db: AsyncSession, actor: User
    ) -> Product:
        product = await ProductService.get_product(product_id, db)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(product, field, value)
        db.add(AuditLog(
            user_id=actor.id,
            action="UPDATE_PRODUCT",
            entity="Product",
            entity_id=str(product_id),
        ))
        await db.commit()
        await db.refresh(product)
        return product

    @staticmethod
    async def deactivate_product(product_id: int, db: AsyncSession, actor: User) -> dict:
        product = await ProductService.get_product(product_id, db)

        stock_result = await db.execute(
            select(func.coalesce(func.sum(Stock.quantity), 0)).where(Stock.product_id == product_id)
        )
        total = stock_result.scalar() or 0
        if total > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Нельзя удалить товар: на складе есть остатки ({total} ед.)",
            )

        product.is_active = False
        db.add(AuditLog(
            user_id=actor.id,
            action="DEACTIVATE_PRODUCT",
            entity="Product",
            entity_id=str(product_id),
            detail={"sku": product.sku, "name": product.name},
        ))
        await db.commit()
        return {"detail": "Товар деактивирован"}

    @staticmethod
    async def bulk_import_products(
        items: list[ProductCreate],
        db: AsyncSession,
        actor: User,
        *,
        skip_duplicates: bool = True,
    ) -> ProductImportResult:
        created = 0
        skipped = 0
        errors: list[str] = []

        existing_res = await db.execute(select(Product.sku))
        existing_skus = {s.upper() for s in existing_res.scalars().all()}

        for i, data in enumerate(items, start=1):
            sku = data.sku.upper()
            if sku in existing_skus:
                if skip_duplicates:
                    skipped += 1
                    continue
                errors.append(f"Строка {i}: товар со SKU «{sku}» уже существует")
                continue

            try:
                product = Product(**data.model_dump())
                db.add(product)
                existing_skus.add(sku)
                created += 1
            except Exception as exc:
                errors.append(f"Строка {i}: {exc}")

        if created > 0:
            db.add(AuditLog(
                user_id=actor.id,
                action="BULK_IMPORT_PRODUCTS",
                entity="Product",
                detail={"created": created, "skipped": skipped, "errors": len(errors)},
            ))
            await db.commit()
        elif errors:
            await db.rollback()
        else:
            await db.rollback()

        return ProductImportResult(created=created, skipped=skipped, errors=errors)
