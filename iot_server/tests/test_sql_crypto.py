from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from api import routes
from crypto import audit
from crypto.cipher import CryptoError
from db import models as m
from db.seed import seed_database
from main import app
from repositories.sql import SqlRepository
from schemas.telemetry import ShelfPacket
from services import shelf

API = '/api/v1'


@pytest.fixture
def db_url(tmp_path):
    url = f'sqlite:///{tmp_path / "iot.db"}'
    engine = create_engine(url)
    m.Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_database(s)
    factory = sessionmaker(
        bind=create_engine(url, connect_args={'check_same_thread': False}),
        expire_on_commit=False)
    routes.use_sql(factory)
    SqlRepository.reset_state()
    yield url
    routes.use_memory()
    SqlRepository.reset_state()


@pytest.fixture
def client(db_url):
    return TestClient(app)


def post_shelf(client, shelf_id, weight, minute):
    return client.post(f'{API}/telemetry/shelf', json={
        'shelf_id': shelf_id, 'weight_g': weight,
        'timestamp': f'2026-10-08T10:{minute:02d}:00Z'})


def count_audit(url):
    with Session(create_engine(url)) as s:
        return s.scalar(select(func.count()).select_from(m.AuditLog))


def test_payload_is_not_readable_in_db(client, db_url):
    post_shelf(client, 'A1-1-1', 2000.0, 0)
    with Session(create_engine(db_url)) as s:
        blob = s.scalars(select(m.Measurement.payload)).one()
    assert b'weight_g' not in blob and b'2000' not in blob
    assert blob[0] == 1  # версия ключа


def test_alert_details_are_encrypted(client, db_url):
    assert post_shelf(client, 'X9-9-9', 100.0, 0).status_code == 404
    with Session(create_engine(db_url)) as s:
        raw = s.scalars(select(m.Alert.details)).one()
    assert 'Неизвестная'.encode() not in raw
    assert client.get(f'{API}/alerts').json()[0]['details'] == 'Неизвестная полка'


def test_tampered_payload_detected(client, db_url):
    post_shelf(client, 'A1-1-1', 2000.0, 0)
    engine = create_engine(db_url)
    with Session(engine) as s:
        r = s.scalars(select(m.Measurement)).one()
        r.payload = r.payload[:-1] + bytes([r.payload[-1] ^ 1])
        s.commit()
    with Session(engine) as s:
        with pytest.raises(CryptoError):
            SqlRepository(s).list_measurements(10)


def test_payload_moved_to_other_row_detected(client, db_url):
    post_shelf(client, 'A1-1-1', 2000.0, 0)
    post_shelf(client, 'A1-1-1', 1600.0, 1)
    engine = create_engine(db_url)
    with Session(engine) as s:
        a, b = s.scalars(select(m.Measurement).order_by(m.Measurement.id)).all()
        a.payload, b.payload = b.payload, a.payload
        s.commit()
    with Session(engine) as s:
        with pytest.raises(CryptoError):
            SqlRepository(s).list_measurements(10)


def test_audit_rolls_back_with_stock(client, db_url):
    post_shelf(client, 'A1-1-1', 2000.0, 0)
    before = count_audit(db_url)
    p = ShelfPacket(shelf_id='A1-1-1', weight_g=1600.0,
                    timestamp=datetime(2026, 10, 8, 10, 1, tzinfo=timezone.utc))
    with pytest.raises(RuntimeError):
        with routes.unit_of_work() as r:
            assert shelf.process(p, r)['new_stock'] == 8
            raise RuntimeError('сбой после обновления остатка')
    assert count_audit(db_url) == before
    rows = client.get(f'{API}/inventory').json()
    assert next(x for x in rows if x['shelf_id'] == 'A1-1-1')['quantity'] == 10


def test_audit_chain_valid_after_requests(client, db_url):
    post_shelf(client, 'A1-1-1', 2000.0, 0)
    post_shelf(client, 'A1-1-1', 1600.0, 1)
    post_shelf(client, 'X9-9-9', 100.0, 2)
    assert count_audit(db_url) == 3
    with Session(create_engine(db_url)) as s:
        assert audit.verify_chain(s) is None