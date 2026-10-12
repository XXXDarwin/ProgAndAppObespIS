from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.ml import DemandHistoryImport
from app.schemas.products import ProductImportItem
from app.schemas.warehouse import CellBulkCreate


class BootstrapOrderLine(BaseModel):
    sku: str
    quantity: int = Field(gt=0)
    cell_address: Optional[str] = None
    to_cell_address: Optional[str] = None
    cell_zone: Optional[str] = None
    cell_rack: Optional[int] = None
    cell_shelf: Optional[int] = None
    cell_position: Optional[int] = None
    to_cell_zone: Optional[str] = None
    to_cell_rack: Optional[int] = None
    to_cell_shelf: Optional[int] = None
    to_cell_position: Optional[int] = None


class BootstrapTimedOrder(BaseModel):
    type: Literal["ARRIVAL", "CONSUMPTION", "INVENTORY", "MOVE"]
    date: date
    comment: Optional[str] = None
    items: List[BootstrapOrderLine] = []


class BootstrapTimedOrdersResult(BaseModel):
    arrivals: int = 0
    consumptions: int = 0
    inventories: int = 0
    moves: int = 0
    arrival_items: int = 0
    consumption_items: int = 0
    inventory_items: int = 0
    warnings: List[str] = []


class BootstrapStockLine(BaseModel):
    sku: str
    cell_address: str
    quantity: int = Field(gt=0)
    cell_zone: Optional[str] = None
    cell_rack: Optional[int] = None
    cell_shelf: Optional[int] = None
    cell_position: Optional[int] = None


class WarehouseBootstrapRequest(BaseModel):
    """Единая загрузка согласованных данных склада (генератор)."""
    comment: Optional[str] = "Импорт из генератора данных"
    cells: Optional[CellBulkCreate] = None
    products: List[ProductImportItem] = []
    skip_existing_products: bool = True
    initial_stock: List[BootstrapStockLine] = []
    timed_orders: List[BootstrapTimedOrder] = []
    demand_history: Optional[DemandHistoryImport] = None
    run_ml_training: bool = False


class WarehouseBootstrapResult(BaseModel):
    cells_created: int = 0
    cells_skipped: int = 0
    cells_reactivated: int = 0
    products_created: int = 0
    products_skipped: int = 0
    stock_lines_applied: int = 0
    arrival_orders_completed: int = 0
    timed_arrivals: int = 0
    timed_consumptions: int = 0
    timed_inventories: int = 0
    timed_moves: int = 0
    timed_inventory_items: int = 0
    history_orders: int = 0
    history_items: int = 0
    ml_training_started: bool = False
    warnings: List[str] = []
