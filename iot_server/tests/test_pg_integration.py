import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from api import routes
from db.seed import seed_database
from db.session import get_url
from main import app
from repositories.sql import SqlRepository
from schemas.telemetry import ShelfPacket
from services import shelf

API = '/api/v1'
TEST_DB = 'iot_test'
SERVER_DIR = Path(__file__).resolve().parent.parent
TABLES = {'products', 'storage_cells', 'stocks', 'devices', 'sensors',
          'measurements', 'alerts', 'audit_log'}


@pytest.fixture(scope='module')
def pg_url():
    base = make_url(get_url())
    admin = create_engine(base, isolation_level='AUTOCOMMIT')
    try:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)'))
            c.execute(text(f'CREATE DATABASE {TEST_DB}'))
    except Exception as e:
        pytest.skip(f'PostgreSQL недоступен: {e}')
    finally:
        admin.dispose()
    url = base.set(database=TEST_DB).render_as_string(hide_password=False)
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                   cwd=SERVER_DIR, check=True,
                   env={**__import__('os').environ, 'IOT_DATABASE_URL': url})
    return url


@pytest.fixture
def factory(pg_url):
    engine = create_engine(pg_url)
    with engine.begin() as c:
        c.execute(text('TRUNCATE products, storage_cells, stocks, devices, '
                       'sensors, measurements, alerts, audit_log '
                       'RESTART IDENTITY CASCADE'))
    f = sessionmaker(bind=engine, expire_on_commit=False)
    with f() as s:
        seed_database(s)
    routes.use_sql(f)
    SqlRepository.reset_state()
    yield f
    routes.use_memory()
    SqlRepository.reset_state()
    engine.dispose()


@pytest.fixture
def client(factory):
    return TestClient(app)


def post_shelf(client, weight, minute):
    return client.post(f'{API}/telemetry/shelf', json={
        'shelf_id': 'A1-1-1', 'weight_g': weight,
        'timestamp': f'2026-10-08T10:{minute:02d}:00Z'})


def stock(client):
    rows = client.get(f'{API}/inventory').json()
    return next(r for r in rows if r['shelf_id'] == 'A1-1-1')


def test_migration_creates_8_tables(pg_url):
    engine = create_engine(pg_url)
    names = set(inspect(engine).get_table_names())
    engine.dispose()
    assert TABLES <= names


def test_write_and_read_cycle_pg(client):
    assert post_shelf(client, 2000.0, 0).json() == {'status': 'BASELINE'}
    r = post_shelf(client, 1600.0, 1)
    assert r.json() == {'status': 'SUCCESS', 'delta_items': -2, 'new_stock': 8}
    assert stock(client)['quantity'] == 8
    data = client.get(f'{API}/telemetry').json()
    assert len(data) == 2 and data[0]['weight_g'] == 1600.0


def test_data_survives_restart_pg(client, pg_url):
    post_shelf(client, 2000.0, 0)
    post_shelf(client, 1600.0, 1)
    engine = create_engine(pg_url)  # «перезапуск»: новое подключение
    routes.use_sql(sessionmaker(bind=engine, expire_on_commit=False))
    assert stock(client)['quantity'] == 8
    assert len(client.get(f'{API}/telemetry').json()) == 2
    engine.dispose()


def test_rollback_on_error_pg(client):
    post_shelf(client, 2000.0, 0)
    p = ShelfPacket(shelf_id='A1-1-1', weight_g=1600.0,
                    timestamp=datetime(2026, 10, 8, 10, 1, tzinfo=timezone.utc))
    with pytest.raises(RuntimeError):
        with routes.unit_of_work() as r:
            assert shelf.process(p, r)['new_stock'] == 8
            raise RuntimeError('сбой после обновления остатка')
    assert stock(client)['quantity'] == 10
    assert len(client.get(f'{API}/telemetry').json()) == 1


def test_duplicate_packet_409_pg(client):
    assert post_shelf(client, 2000.0, 0).status_code == 200
    assert post_shelf(client, 2000.0, 0).status_code == 409


def test_select_for_update_blocks_second_writer(factory):
    a = factory()
    SqlRepository(a).get_shelf('A1-1-1')  # A держит блокировку строки stocks
    result = {}

    def second():
        with factory() as b:
            b.execute(text("SET LOCAL lock_timeout = '300ms'"))
            try:
                SqlRepository(b).get_shelf('A1-1-1')
                result['blocked'] = False
            except DBAPIError:
                result['blocked'] = True

    t = threading.Thread(target=second)
    t.start()
    t.join()
    a.commit()
    a.close()
    assert result['blocked'] is True
    with factory() as c:  # после commit блокировка снята
        assert SqlRepository(c).get_shelf('A1-1-1') is not None