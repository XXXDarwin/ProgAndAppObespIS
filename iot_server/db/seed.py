import config
from sqlalchemy import select

from db import models as m
from db.session import make_session_factory

HUB_ID = 'HUB-01'  # device_id эмулятора (config.yaml, hub.device_id)


def _one(db, model, **where):
    return db.scalar(select(model).filter_by(**where))


def seed_database(db):
    dev = _one(db, m.Device, device_id=HUB_ID)
    if dev is None:
        # secret_enc: заглушка, на этапе 7 заменяется зашифрованным ключом хаба
        dev = m.Device(device_id=HUB_ID, secret_enc=b'', firmware_version='emu-1.0')
        db.add(dev)
        db.flush()
    for zone in config.SEED_ZONES:
        if _one(db, m.Sensor, kind='climate', code=zone) is None:
            db.add(m.Sensor(device_id=dev.id, kind='climate', code=zone))
    for shelf_id, s in config.SEED_SHELVES.items():
        product = _one(db, m.Product, name=s['product'])
        if product is None:
            product = m.Product(name=s['product'], unit_weight_g=s['unit_weight_g'])
            db.add(product)
            db.flush()
        cell = _one(db, m.StorageCell, shelf_id=shelf_id)
        if cell is None:
            cell = m.StorageCell(shelf_id=shelf_id, zone=s['zone'])
            db.add(cell)
            db.flush()
        if _one(db, m.Stock, cell_id=cell.id) is None:
            db.add(m.Stock(cell_id=cell.id, product_id=product.id,
                           quantity=s['quantity']))
        if _one(db, m.Sensor, kind='shelf', code=shelf_id) is None:
            db.add(m.Sensor(device_id=dev.id, kind='shelf', code=shelf_id,
                            cell_id=cell.id))
    db.commit()


if __name__ == '__main__':
    with make_session_factory()() as session:
        seed_database(session)
    print('Seed выполнен')