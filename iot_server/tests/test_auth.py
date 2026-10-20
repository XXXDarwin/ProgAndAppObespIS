import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from api import routes
from crypto import audit, signing
from db import models as m
from db.seed import seed_database
from main import app
from repositories.sql import SqlRepository

API = '/api/v1'
SECRET = bytes.fromhex('aa' * 32)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('IOT_HUB_SECRET', SECRET.hex())
    url = f'sqlite:///{tmp_path / "iot.db"}'
    engine = create_engine(url)
    m.Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_database(s)
    factory = sessionmaker(
        bind=create_engine(url, connect_args={'check_same_thread': False}),
        expire_on_commit=False)
    routes.use_sql(factory)
    routes.use_auth(True)
    SqlRepository.reset_state()
    yield TestClient(app), url
    routes.use_auth(False)
    routes.use_memory()
    SqlRepository.reset_state()


def now_iso(delta_s=0):
    t = datetime.now(timezone.utc) + timedelta(seconds=delta_s)
    return t.isoformat(timespec='seconds')


def packet(minute=0):
    return {'shelf_id': 'A1-1-1', 'weight_g': 2000.0,
            'timestamp': f'2026-10-08T10:{minute:02d}:00Z'}


def send(client, seq, body=None, ts=None, secret=SECRET, device='HUB-01',
         signed_body=None):
    raw = json.dumps(body or packet()).encode()
    ts = ts or now_iso()
    headers = {'Content-Type': 'application/json', 'X-Device-Id': device,
               'X-Seq': str(seq), 'X-Timestamp': ts,
               'X-Signature': signing.sign(secret, signed_body or raw, ts, seq)}
    return client.post(f'{API}/telemetry/shelf', content=raw, headers=headers)


def test_valid_signature_accepted(env):
    client, _ = env
    r = send(client, 1)
    assert r.status_code == 200 and r.json() == {'status': 'BASELINE'}


def test_missing_headers_rejected(env):
    client, _ = env
    r = client.post(f'{API}/telemetry/shelf', json=packet())
    assert r.status_code == 401
    assert client.get(f'{API}/telemetry').json() == []


def test_wrong_secret_rejected(env):
    client, _ = env
    assert send(client, 1, secret=bytes.fromhex('bb' * 32)).status_code == 401
    assert client.get(f'{API}/telemetry').json() == []


def test_tampered_body_rejected(env):
    client, _ = env
    other = json.dumps({**packet(), 'weight_g': 1.0}).encode()
    assert send(client, 1, signed_body=other).status_code == 401


def test_stale_timestamp_rejected(env):
    client, _ = env
    assert send(client, 1, ts=now_iso(-120)).status_code == 401


def test_replayed_seq_rejected(env):
    client, _ = env
    assert send(client, 10).status_code == 200
    assert send(client, 10, body=packet(1)).status_code == 409
    assert len(client.get(f'{API}/telemetry').json()) == 1


def test_lower_seq_rejected(env):
    client, _ = env
    assert send(client, 10).status_code == 200
    assert send(client, 9, body=packet(1)).status_code == 409


def test_unknown_device_rejected(env):
    client, _ = env
    assert send(client, 1, device='HUB-99').status_code == 401


def test_failures_are_audited_and_chain_valid(env):
    client, url = env
    send(client, 1, secret=bytes.fromhex('bb' * 32))
    with Session(create_engine(url)) as s:
        events = list(s.scalars(select(m.AuditLog.event)))
        assert events and events[0].startswith('auth_fail:HUB-01')
        assert audit.verify_chain(s) is None


def test_device_secret_is_encrypted_in_db(env):
    _, url = env
    with Session(create_engine(url)) as s:
        blob = s.scalars(select(m.Device.secret_enc)).one()
    assert SECRET not in blob and blob[0] == 1