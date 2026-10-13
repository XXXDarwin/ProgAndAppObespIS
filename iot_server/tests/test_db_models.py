from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import (Base, Device, Measurement, Product, Sensor, Stock,
                       StorageCell)

TS = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def add_device(db):
    dev = Device(device_id='HUB-01', secret_enc=b'x')
    db.add(dev)
    db.flush()
    return dev


def add_sensor(db, dev, kind='climate', code='A'):
    sensor = Sensor(device_id=dev.id, kind=kind, code=code)
    db.add(sensor)
    db.flush()
    return sensor


def test_eight_tables():
    assert set(Base.metadata.tables) == {
        'products', 'storage_cells', 'stocks', 'devices',
        'sensors', 'measurements', 'alerts', 'audit_log'}


def test_chain_measurement_sensor_device(db):
    dev = add_device(db)
    sensor = add_sensor(db, dev)
    db.add(Measurement(sensor_id=sensor.id, kind='climate', source='A',
                       ts=TS, payload=b'{"t": 22.5}'))
    db.commit()
    m = db.scalar(select(Measurement))
    s = db.get(Sensor, m.sensor_id)
    d = db.get(Device, s.device_id)
    assert m.payload == b'{"t": 22.5}'
    assert d.device_id == 'HUB-01'


def test_sensor_kind_code_unique(db):
    dev = add_device(db)
    add_sensor(db, dev)
    with pytest.raises(IntegrityError):
        add_sensor(db, dev)


def test_measurement_duplicate_rejected(db):
    dev = add_device(db)
    sensor = add_sensor(db, dev)
    for _ in range(2):
        db.add(Measurement(sensor_id=sensor.id, kind='climate', source='A',
                           ts=TS, payload=b'x'))
    with pytest.raises(IntegrityError):
        db.flush()


def test_one_stock_per_cell(db):
    cell = StorageCell(shelf_id='A1-1-1', zone='A')
    prod = Product(name='Резистор-набор', unit_weight_g=200.0)
    db.add_all([cell, prod])
    db.flush()
    db.add(Stock(cell_id=cell.id, product_id=prod.id, quantity=10))
    db.flush()
    db.add(Stock(cell_id=cell.id, product_id=prod.id, quantity=5))
    with pytest.raises(IntegrityError):
        db.flush()