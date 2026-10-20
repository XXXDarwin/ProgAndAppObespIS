import json
from datetime import datetime, timezone

from sqlalchemy import select

import config
from crypto import audit, cipher
from db import models as m
from domain.models import Alert, Shelf, ZoneLimits
from repositories.base import Repository


class UnknownSensor(Exception):
    '''В БД нет датчика для пары (kind, code): ответ 404.'''


def _utc(ts):
    if ts.tzinfo is None:  # SQLite возвращает время без пояса
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _aad(*parts):
    return '|'.join(str(x) for x in parts).encode()


class ShelfRecord:
    '''Полка для сервисов: читает из БД, а quantity и last_weight_g пишет в строку stocks.'''

    def __init__(self, cell, product, stock):
        self._stock = stock
        self.shelf_id = cell.shelf_id
        self.zone = cell.zone
        self.product_name = product.name
        self.unit_weight_g = product.unit_weight_g

    @property
    def quantity(self):
        return self._stock.quantity

    @quantity.setter
    def quantity(self, value):
        self._stock.quantity = value

    @property
    def last_weight_g(self):
        return self._stock.last_weight_g

    @last_weight_g.setter
    def last_weight_g(self, value):
        self._stock.last_weight_g = value


class SqlRepository(Repository):
    # статусы зон: рабочее состояние процесса, в БД не хранится (как буфер preprocess)
    _status = {}

    def __init__(self, db):
        self.db = db

    @classmethod
    def reset_state(cls):
        cls._status.clear()

    # --- криптография: AES-256-GCM, ключ вне БД ---
    def _seal(self, plain, purpose, aad):
        return cipher.encrypt(plain, purpose, aad)

    def _open(self, blob, purpose, aad):
        return cipher.decrypt(blob, purpose, aad)

    # --- зоны и статусы ---
    def get_zone(self, zone):
        lim = config.SEED_ZONES.get(zone)
        return ZoneLimits(zone=zone, **lim) if lim else None

    def get_status(self, zone):
        return self._status.get(zone)

    def set_status(self, zone, status):
        self._status[zone] = status

    def list_statuses(self):
        return dict(self._status)

    # --- полки ---
    def _shelf_query(self):
        return (select(m.Stock, m.StorageCell, m.Product)
                .join(m.StorageCell, m.Stock.cell_id == m.StorageCell.id)
                .join(m.Product, m.Stock.product_id == m.Product.id))

    def get_shelf(self, shelf_id):
        q = (self._shelf_query()
             .where(m.StorageCell.shelf_id == shelf_id)
             .with_for_update(of=m.Stock))
        row = self.db.execute(q).first()
        if row is None:
            return None
        stock, cell, product = row
        return ShelfRecord(cell, product, stock)

    def list_shelves(self):
        rows = self.db.execute(self._shelf_query().order_by(m.StorageCell.id))
        return [Shelf(shelf_id=c.shelf_id, zone=c.zone, product_name=p.name,
                      unit_weight_g=p.unit_weight_g, quantity=s.quantity,
                      last_weight_g=s.last_weight_g)
                for s, c, p in rows]

    # --- пакеты и измерения ---
    def register_packet(self, shelf_id, ts):
        q = select(m.Measurement.id).where(
            m.Measurement.kind == 'shelf', m.Measurement.source == shelf_id,
            m.Measurement.ts == _utc(ts))
        return self.db.scalar(q) is None

    def save_measurement(self, kind, packet):
        src = packet.zone if kind == 'climate' else packet.shelf_id
        sensor = self.db.scalar(select(m.Sensor).where(
            m.Sensor.kind == kind, m.Sensor.code == src))
        if sensor is None:
            raise UnknownSensor(src)
        ts = _utc(packet.timestamp)
        plain = packet.model_dump_json(exclude={'timestamp'}).encode()
        blob = self._seal(plain, 'measurements', _aad(kind, src, ts.isoformat()))
        self.db.add(m.Measurement(sensor_id=sensor.id, kind=kind, source=src,
                                  ts=ts, payload=blob))
        self.db.flush()  # нарушение UNIQUE проявится здесь
        audit.append(self.db, f'measurement:{kind}:{src}')

    def list_measurements(self, limit):
        rows = self.db.scalars(select(m.Measurement)
                               .order_by(m.Measurement.id.desc()).limit(limit))
        out = []
        for r in rows:
            ts = _utc(r.ts)
            plain = self._open(r.payload, 'measurements',
                               _aad(r.kind, r.source, ts.isoformat()))
            out.append({'kind': r.kind, **json.loads(plain),
                        'timestamp': ts.isoformat().replace('+00:00', 'Z')})
        return out

    # --- предупреждения ---
    def add_alert(self, type_, severity, source, details):
        created = datetime.now(timezone.utc)
        blob = None
        if details is not None:
            blob = self._seal(str(details).encode(), 'alerts',
                              _aad(type_, source, created.isoformat()))
        row = m.Alert(type=type_, severity=severity, source=source,
                      details=blob, created=created)
        self.db.add(row)
        self.db.flush()
        audit.append(self.db, f'alert:{type_}:{source}')
        return Alert(id=row.id, type=type_, severity=severity, source=source,
                     details=details, created=created)

    def list_alerts(self, severity=None, limit=50):
        q = select(m.Alert).order_by(m.Alert.id.desc()).limit(limit)
        if severity is not None:
            q = q.where(m.Alert.severity == severity)
        out = []
        for r in self.db.scalars(q):
            created = _utc(r.created)
            details = None
            if r.details is not None:
                details = self._open(r.details, 'alerts',
                                     _aad(r.type, r.source, created.isoformat())).decode()
            out.append(Alert(id=r.id, type=r.type, severity=r.severity,
                             source=r.source, details=details, created=created))
        return out