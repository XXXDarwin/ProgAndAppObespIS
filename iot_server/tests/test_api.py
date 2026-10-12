# iot_server/tests/test_api.py
import pytest
from fastapi.testclient import TestClient

from api import routes
from main import app
from repositories.memory import MemoryRepository
from services import preprocess

CLIMATE = '/api/v1/telemetry/climate'
SHELF = '/api/v1/telemetry/shelf'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(routes, 'repo', MemoryRepository(seed=True))
    preprocess.buffers.clear()
    yield TestClient(app)
    preprocess.buffers.clear()


def climate_body(**kw):
    body = {'zone': 'A', 'temperature': 22.5, 'humidity': 45.0,
            'timestamp': '2026-10-08T10:00:00Z'}
    body.update(kw)
    return body


def shelf_body(w, ts, shelf_id='A1-1-1'):
    return {'shelf_id': shelf_id, 'weight_g': w, 'timestamp': ts}


def test_health(client):
    assert client.get('/health').json() == {'status': 'ok'}
    assert client.get('/api/v1/health').status_code == 200


def test_climate_ok(client):
    r = client.post(CLIMATE, json=climate_body())
    assert r.status_code == 200
    assert r.json()['status'] == 'NORMAL'


def test_climate_invalid_type_422(client):
    r = client.post(CLIMATE, json=climate_body(temperature='hello'))
    assert r.status_code == 422


def test_climate_out_of_range_422(client):
    r = client.post(CLIMATE, json=climate_body(temperature=200))
    assert r.status_code == 422


def test_climate_unknown_zone_404(client):
    r = client.post(CLIMATE, json=climate_body(zone='Z'))
    assert r.status_code == 404


def test_shelf_flow_success(client):
    r1 = client.post(SHELF, json=shelf_body(2000.0, '2026-10-08T10:00:00Z'))
    assert r1.json() == {'status': 'BASELINE'}
    r2 = client.post(SHELF, json=shelf_body(1600.0, '2026-10-08T10:01:00Z'))
    assert r2.status_code == 200
    assert r2.json() == {'status': 'SUCCESS', 'delta_items': -2, 'new_stock': 8}


def test_shelf_duplicate_409(client):
    body = shelf_body(2000.0, '2026-10-08T10:00:00Z')
    assert client.post(SHELF, json=body).status_code == 200
    assert client.post(SHELF, json=body).status_code == 409


def test_shelf_unknown_404(client):
    r = client.post(SHELF, json=shelf_body(100.0, '2026-10-08T10:00:00Z',
                                           shelf_id='X9-9-9'))
    assert r.status_code == 404


def test_shelf_anomaly_returns_200(client):
    client.post(SHELF, json=shelf_body(2000.0, '2026-10-08T10:00:00Z'))
    r = client.post(SHELF, json=shelf_body(1720.0, '2026-10-08T10:01:00Z'))
    assert r.status_code == 200
    assert r.json()['status'] == 'ANOMALY'


def test_inventory(client):
    r = client.get('/api/v1/inventory')
    assert r.status_code == 200
    ids = [s['shelf_id'] for s in r.json()]
    assert 'A1-1-1' in ids and 'A1-1-2' in ids


def test_alerts_filter(client):
    client.post(SHELF, json=shelf_body(100.0, '2026-10-08T10:00:00Z',
                                       shelf_id='X9-9-9'))
    high = client.get('/api/v1/alerts', params={'severity': 'HIGH'}).json()
    assert [a['type'] for a in high] == ['UNKNOWN_SHELF']
    medium = client.get('/api/v1/alerts', params={'severity': 'MEDIUM'}).json()
    assert medium == []


def test_climate_status_and_telemetry(client):
    client.post(CLIMATE, json=climate_body())
    assert client.get('/api/v1/climate/status').status_code == 200
    r = client.get('/api/v1/telemetry', params={'limit': 10})
    assert r.status_code == 200
    assert len(r.json()) == 1