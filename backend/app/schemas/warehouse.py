from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, field_validator

from app.models.models import OrderType, OrderStatus


# ─── Storage Cell ─────────────────────────────────────────────────────────────

class CellBase(BaseModel):
    zone: str
    rack: int
    shelf: int
    position: int
    max_capacity: int = 100


class CellCreate(CellBase):
    @field_validator("zone")
    @classmethod
    def zone_upper(cls, v: str) -> str:
        return v.strip().upper()


class CellBulkCreate(BaseModel):
    """Массовое создание ячеек по зонам."""
    zones: List[str]          # ["A", "B", "C"]
    racks_per_zone: int       # стеллажей в зоне
    shelves_per_rack: int     # полок на стеллаже
    positions_per_shelf: int  # позиций на полке
    max_capacity: int = 100


class CellOut(BaseModel):
    id: int
    zone: str
    rack: int
    shelf: int
    position: int
    max_capacity: int
    is_active: bool
    address: str              # computed property из модели

    model_config = {"from_attributes": True}


class CellWithStock(CellOut):
    current_stock: int = 0    # суммарное кол-во товаров в ячейке
    free_capacity: int = 0


# ─── Stock ────────────────────────────────────────────────────────────────────

class ProductBrief(BaseModel):
    id: int
    sku: str
    name: str

    model_config = {"from_attributes": True}


class StockOut(BaseModel):
    product_id: int
    cell_id: int
    quantity: int
    updated_at: datetime
    product: Optional[ProductBrief] = None
    cell: Optional[CellOut] = None

    model_config = {"from_attributes": True}


class StockByProduct(BaseModel):
    """Остатки одного товара по всем ячейкам."""
    product_id: int
    sku: str
    name: str
    total_quantity: int
    cells: List[StockOut]

#
# ─── Move stock ───────────────────────────────────────────────────────────────
#

class StockMoveRequest(BaseModel):
    product_id: int
    from_cell_id: int
    to_cell_id: int
    quantity: int

    @field_validator("quantity")
    @classmethod
    def qty_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Количество должно быть больше 0")
        return v


class StockMoveResponse(BaseModel):
    detail: str
    product_id: int
    from_cell_id: int
    to_cell_id: int
    moved: int


class MoveLogOut(BaseModel):
    id: int
    created_at: datetime
    username: Optional[str] = None
    product_id: int
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    from_cell_id: int
    from_cell_address: Optional[str] = None
    to_cell_id: int
    to_cell_address: Optional[str] = None
    quantity: int


# ─── Order Items ──────────────────────────────────────────────────────────────

class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int
    cell_id: Optional[int] = None       # для приёмки — куда класть; для расхода — откуда брать

    @field_validator("quantity")
    @classmethod
    def qty_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Количество должно быть больше 0")
        return v


class OrderItemOut(BaseModel):
    id: int
    product_id: int
    cell_id: Optional[int]
    quantity: int
    quantity_fact: Optional[int]

    # Вложенные объекты для удобства фронта
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    cell_address: Optional[str] = None

    model_config = {"from_attributes": True}


# ─── Orders ───────────────────────────────────────────────────────────────────

class OrderCreate(BaseModel):
    type: OrderType
    comment: Optional[str] = None
    items: List[OrderItemCreate]


class ArrivalCreate(BaseModel):
    """Специализированная схема для приёмки."""
    comment: Optional[str] = None
    items: List[OrderItemCreate]   # cell_id опционален — алгоритм подберёт


class ArrivalImportItem(BaseModel):
    sku: str
    quantity: int
    cell_address: Optional[str] = None

    @field_validator("quantity")
    @classmethod
    def qty_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Количество должно быть больше 0")
        return v


class ArrivalImportPayload(BaseModel):
    comment: Optional[str] = None
    items: List[ArrivalImportItem]


class ArrivalCompleteItem(BaseModel):
    order_item_id: int
    quantity: int
    cell_id: Optional[int] = None

    @field_validator("quantity")
    @classmethod
    def qty_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Количество должно быть больше 0")
        return v


class ArrivalComplete(BaseModel):
    items: List[ArrivalCompleteItem]


class ConsumptionCreate(BaseModel):
    """Специализированная схема для расхода."""
    comment: Optional[str] = None
    items: List[OrderItemCreate]   # quantity — сколько нужно отгрузить


class ConsumptionImportItem(BaseModel):
    sku: str
    quantity: int

    @field_validator("quantity")
    @classmethod
    def qty_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Количество должно быть больше 0")
        return v


class ConsumptionImportPayload(BaseModel):
    comment: Optional[str] = None
    items: List[ConsumptionImportItem]


class InventoryCreate(BaseModel):
    """Инвентаризация: список товаров для пересчёта."""
    comment: Optional[str] = None
    product_ids: Optional[List[int]] = None   # None = все товары


class InventoryFactItem(BaseModel):
    """Ввод фактических данных при инвентаризации."""
    order_item_id: int
    quantity_fact: int

    @field_validator("quantity_fact")
    @classmethod
    def qty_not_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Фактическое количество не может быть отрицательным")
        return v


class InventoryConfirm(BaseModel):
    fact_items: List[InventoryFactItem]


class InventoryTaskOut(BaseModel):
    id: int
    order_id: int
    zone: str
    rack: int
    label: str
    status: OrderStatus
    items_total: int = 0
    items_counted: int = 0
    loss_units: int = 0
    surplus_units: int = 0


class InventoryDiscrepancyOut(BaseModel):
    order_item_id: int
    product_sku: str
    product_name: str
    cell_address: str
    zone: str
    rack: int
    expected: int
    fact: int
    delta: int
    kind: str  # loss | surplus


class InventoryLossSummaryOut(BaseModel):
    order_id: int
    status: OrderStatus
    tasks_total: int
    tasks_completed: int
    total_loss_units: int
    total_surplus_units: int
    discrepancies: List[InventoryDiscrepancyOut]


class OrderOut(BaseModel):
    id: int
    type: OrderType
    status: OrderStatus
    comment: Optional[str]
    created_at: datetime
    closed_at: Optional[datetime]
    created_by: Optional[str] = None   # username
    items: List[OrderItemOut] = []

    model_config = {"from_attributes": True}


# ─── Route Sheet ──────────────────────────────────────────────────────────────

class RouteSheetItem(BaseModel):
    step: int
    order_item_id: Optional[int] = None
    cell_address: str
    zone: str
    rack: int
    shelf: int
    position: int
    product_sku: str
    product_name: str
    quantity: int
    quantity_fact: Optional[int] = None


class RouteSheet(BaseModel):
    order_id: int
    total_items: int
    route: List[RouteSheetItem]
