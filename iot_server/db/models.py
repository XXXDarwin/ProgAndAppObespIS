from datetime import datetime

from sqlalchemy import (BigInteger, DateTime, Float, ForeignKey, Integer,
                        LargeBinary, String, UniqueConstraint, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# BigInteger автоинкрементится в PostgreSQL; в SQLite (тесты) нужен Integer
BigPk = BigInteger().with_variant(Integer, 'sqlite')


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = 'products'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    unit_weight_g: Mapped[float] = mapped_column(Float)


class StorageCell(Base):
    __tablename__ = 'storage_cells'
    id: Mapped[int] = mapped_column(primary_key=True)
    shelf_id: Mapped[str] = mapped_column(String(32), unique=True)
    zone: Mapped[str] = mapped_column(String(8))


class Stock(Base):
    __tablename__ = 'stocks'
    id: Mapped[int] = mapped_column(primary_key=True)
    cell_id: Mapped[int] = mapped_column(ForeignKey('storage_cells.id'), unique=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    quantity: Mapped[int] = mapped_column(Integer)
    last_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)


class Device(Base):
    __tablename__ = 'devices'
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True)
    secret_enc: Mapped[bytes] = mapped_column(LargeBinary)
    last_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Sensor(Base):
    __tablename__ = 'sensors'
    __table_args__ = (UniqueConstraint('kind', 'code'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey('devices.id'))
    kind: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(String(32))
    cell_id: Mapped[int | None] = mapped_column(ForeignKey('storage_cells.id'), nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Measurement(Base):
    __tablename__ = 'measurements'
    __table_args__ = (UniqueConstraint('kind', 'source', 'ts'),)
    id: Mapped[int] = mapped_column(BigPk, primary_key=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey('sensors.id'))
    kind: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(32))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[bytes] = mapped_column(LargeBinary)


class Alert(Base):
    __tablename__ = 'alerts'
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    details: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = 'audit_log'
    id: Mapped[int] = mapped_column(BigPk, primary_key=True)
    event: Mapped[str] = mapped_column(String(200))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash: Mapped[str] = mapped_column(String(64))