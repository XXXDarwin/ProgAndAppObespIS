from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from api import routes
from db import models as m
from db.seed import seed_database
from main import app
from repositories.sql import SqlRepository
from schemas.telemetry import ShelfPacket
from services import shelf

API = '/api/v1'


def make_factory(url):
    engine = create_engine(url, connect_args={'check_same_thread': False})
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def db_url(tmp_path):
    url = f'sqlite:///{tmp_path / "iot.db"}'
    engine = create_engine(url)
    m.Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_database(s)
    routes.use_sql(make_factory(url))
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


def stock_of(client, shelf_id):
    rows = client.get(f'{API}/inventory').json()
    return next(r for r in rows if r['shelf_id'] == shelf_id)


def test_write_and_read_cycle(client):
    assert post_shelf(client, 'A1-1-1', 2000.0, 0).json() == {'status': 'BASELINE'}
    r = post_shelf(client, 'A1-1-1', 1600.0, 1)
    assert r.json() == {'status': 'SUCCESS', 'delta_items': -2, 'new_stock': 8}
    row = stock_of(client, 'A1-1-1')
    assert row['quantity'] == 8 and row['last_weight_g'] == 1600.0
    data = client.get(f'{API}/telemetry').json()
    assert len(data) == 2
    assert data[0]['kind'] == 'shelf' and data[0]['weight_g'] == 1600.0
    assert data[0]['timestamp'] == '2026-10-08T10:01:00Z'


def test_data_survives_restart(client, db_url):
    post_shelf(client, 'A1-1-1', 2000.0, 0)
    post_shelf(client, 'A1-1-1', 1600.0, 1)
    routes.use_sql(make_factory(db_url))  # «перезапуск»: новое подключение к той же БД
    assert stock_of(client, 'A1-1-1')['quantity'] == 8
    assert len(client.get(f'{API}/telemetry').json()) == 2


def test_rollback_on_error(client):
    post_shelf(client, 'A1-1-1', 2000.0, 0)
    p = ShelfPacket(shelf_id='A1-1-1', weight_g=1600.0,
                    timestamp=datetime(2026, 10, 8, 10, 1, tzinfo=timezone.utc))
    with pytest.raises(RuntimeError):
        with routes.unit_of_work() as r:
            assert shelf.process(p, r)['new_stock'] == 8
            raise RuntimeError('сбой после обновления остатка')
    assert stock_of(client, 'A1-1-1')['quantity'] == 10
    assert len(client.get(f'{API}/telemetry').json()) == 1


def test_duplicate_shelf_packet_409(client):
    assert post_shelf(client, 'A1-1-1', 2000.0, 0).status_code == 200
    assert post_shelf(client, 'A1-1-1', 2000.0, 0).status_code == 409


def test_unknown_shelf_404_and_alert_saved(client):
    assert post_shelf(client, 'X9-9-9', 100.0, 0).status_code == 404
    alerts = client.get(f'{API}/alerts').json()
    assert [a['type'] for a in alerts] == ['UNKNOWN_SHELF']


def test_duplicate_climate_packet_409(client):
    body = {'zone': 'B', 'temperature': 22.5, 'humidity': 45.0,
            'timestamp': '2026-10-08T10:00:00Z'}
    assert client.post(f'{API}/telemetry/climate', json=body).status_code == 200
    assert client.post(f'{API}/telemetry/climate', json=body).status_code == 409
    kinds = [x['kind'] for x in client.get(f'{API}/telemetry').json()]
    assert kinds == ['climate']


def test_seed_is_idempotent(db_url):
    with Session(create_engine(db_url)) as s:
        seed_database(s)
        assert s.scalar(select(func.count()).select_from(m.Sensor)) == 4
        assert s.scalar(select(func.count()).select_from(m.Stock)) == 2
        assert s.scalar(select(func.count()).select_from(m.Device)) == 1