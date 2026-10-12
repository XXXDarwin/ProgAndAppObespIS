import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, ForeignKey,
    Enum, Text, JSON, UniqueConstraint, Index, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.database import Base


# ─── Enums ───────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    WORKER = "WORKER"


class OrderType(str, enum.Enum):
    ARRIVAL = "ARRIVAL"
    CONSUMPTION = "CONSUMPTION"
    INVENTORY = "INVENTORY"


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# ─── Users ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), nullable=False, default=UserRole.WORKER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    orders: Mapped[list["Order"]] = relationship("Order", back_populates="created_by_user")
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="user")

    def __repr__(self) -> str:
        return f"<User {self.username} [{self.role}]>"


# ─── Categories ───────────────────────────────────────────────────────────────

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    products: Mapped[list["Product"]] = relationship("Product", back_populates="category")


# ─── Products ─────────────────────────────────────────────────────────────────

class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    weight: Mapped[Optional[float]] = mapped_column(Float)          # кг
    dimensions: Mapped[Optional[dict]] = mapped_column(JSON)        # {"l": 10, "w": 5, "h": 3}
    unit: Mapped[str] = mapped_column(String(32), default="шт")    # шт, кг, л ...
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="products")
    stocks: Mapped[list["Stock"]] = relationship("Stock", back_populates="product")
    order_items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="product")
    predictions: Mapped[list["Prediction"]] = relationship("Prediction", back_populates="product")

    def __repr__(self) -> str:
        return f"<Product {self.sku}: {self.name}>"


# ─── Storage Cells ────────────────────────────────────────────────────────────

class StorageCell(Base):
    __tablename__ = "storage_cells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zone: Mapped[str] = mapped_column(String(8), nullable=False)      # A, B, C ...
    rack: Mapped[int] = mapped_column(Integer, nullable=False)         # 1, 2, 3 ...
    shelf: Mapped[int] = mapped_column(Integer, nullable=False)        # 1, 2, 3 ...
    position: Mapped[int] = mapped_column(Integer, nullable=False)     # 1, 2, 3 ...
    max_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("zone", "rack", "shelf", "position", name="uq_cell_address"),
        Index("ix_cell_zone_rack", "zone", "rack"),
    )

    stocks: Mapped[list["Stock"]] = relationship("Stock", back_populates="cell")

    @property
    def address(self) -> str:
        return f"{self.zone}{self.rack}-{self.shelf}-{self.position}"

    def __repr__(self) -> str:
        return f"<Cell {self.address}>"


# ─── Stocks ───────────────────────────────────────────────────────────────────

class Stock(Base):
    """Текущий остаток конкретного товара в конкретной ячейке."""
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    cell_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("storage_cells.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("product_id", "cell_id", name="uq_stock_product_cell"),
        Index("ix_stock_product", "product_id"),
        Index("ix_stock_cell", "cell_id"),
    )

    product: Mapped["Product"] = relationship("Product", back_populates="stocks")
    cell: Mapped["StorageCell"] = relationship("StorageCell", back_populates="stocks")

    def __repr__(self) -> str:
        return f"<Stock product={self.product_id} cell={self.cell_id} qty={self.quantity}>"


# ─── Orders ───────────────────────────────────────────────────────────────────

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[OrderType] = mapped_column(Enum(OrderType), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_by_user: Mapped[Optional["User"]] = relationship("User", back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    inventory_tasks: Mapped[list["InventoryTask"]] = relationship(
        "InventoryTask", back_populates="order", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Order #{self.id} [{self.type}] {self.status}>"


class InventoryTask(Base):
    """Подзадание инвентаризации: один стеллаж (зона + номер)."""
    __tablename__ = "inventory_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    zone: Mapped[str] = mapped_column(String(8), nullable=False)
    rack: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING
    )
    started_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    order: Mapped["Order"] = relationship("Order", back_populates="inventory_tasks")

    __table_args__ = (
        UniqueConstraint("order_id", "zone", "rack", name="uq_inventory_task_rack"),
        Index("ix_inventory_task_order", "order_id"),
    )

    @property
    def label(self) -> str:
        return f"{self.zone} · Стеллаж {self.rack}"


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    cell_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("storage_cells.id", ondelete="SET NULL"), nullable=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_fact: Mapped[Optional[int]] = mapped_column(Integer)   # для инвентаризации

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped["Product"] = relationship("Product", back_populates="order_items")
    cell: Mapped[Optional["StorageCell"]] = relationship("StorageCell")


# ─── Predictions ─────────────────────────────────────────────────────────────

class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    predicted_value: Mapped[float] = mapped_column(Float, nullable=False)
    lower_bound: Mapped[Optional[float]] = mapped_column(Float)   # доверительный интервал
    upper_bound: Mapped[Optional[float]] = mapped_column(Float)
    model_version: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product: Mapped["Product"] = relationship("Product", back_populates="predictions")

    __table_args__ = (
        Index("ix_prediction_product_date", "product_id", "target_date"),
    )


# ─── Audit Log ───────────────────────────────────────────────────────────────

class AuditLog(Base):
    """Таблица аудита: все действия пользователей."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)   # LOGIN, CREATE_ORDER, ...
    entity: Mapped[Optional[str]] = mapped_column(String(64))          # Order, Product, ...
    entity_id: Mapped[Optional[str]] = mapped_column(String(64))
    detail: Mapped[Optional[dict]] = mapped_column(JSON)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")
