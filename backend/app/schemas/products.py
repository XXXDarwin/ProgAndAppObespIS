from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator


# ─── Category ─────────────────────────────────────────────────────────────────

class CategoryOut(BaseModel):
    id: int
    name: str
    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    name: str


# ─── Product ──────────────────────────────────────────────────────────────────

class ProductBase(BaseModel):
    sku: str
    name: str
    category_id: Optional[int] = None
    weight: Optional[float] = None
    dimensions: Optional[dict] = None   # {"l": 10, "w": 5, "h": 3}
    unit: str = "шт"
    description: Optional[str] = None


class ProductCreate(ProductBase):
    @field_validator("sku")
    @classmethod
    def sku_not_empty(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("SKU не может быть пустым")
        return v


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[int] = None
    weight: Optional[float] = None
    dimensions: Optional[dict] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ProductOut(ProductBase):
    id: int
    sku: str
    is_active: bool
    created_at: datetime
    category: Optional[CategoryOut] = None
    total_stock: Optional[int] = None   # суммарный остаток по всем ячейкам

    model_config = {"from_attributes": True}


class ProductImportItem(BaseModel):
    sku: str
    name: str
    unit: str = "шт"
    category: Optional[str] = None
    weight: Optional[float] = None
    description: Optional[str] = None

    @field_validator("sku")
    @classmethod
    def sku_not_empty(cls, v: str) -> str:
        return v.strip()


class ProductImportPayload(BaseModel):
    items: List[ProductImportItem]
    skip_duplicates: bool = True


class ProductImportResult(BaseModel):
    created: int
    skipped: int
    errors: List[str] = []
