# iot_server/tests/test_shelf.py
from datetime import datetime, timedelta, timezone

import pytest

from repositories.memory import MemoryRepository
from schemas.telemetry import ShelfPacket
from services import shelf
from services.errors import DuplicatePacket, UnknownShelf

T0 = datetime(2026, 10, 8, 10, 0, 0, tzinfo=timezone.utc)
SHELF = 'A1-1-1'  # M1 = 200 г, остаток 10, допуск 6 г


@pytest.fixture
def repo():
    return MemoryRepository(seed=True)


def pkt(w, sec=0, shelf_id=SHELF):
    return ShelfPacket(shelf_id=shelf_id, weight_g=w,
                       timestamp=T0 + timedelta(seconds=sec))


def start(repo, w=2000.0):
    """Первое измерение: базовый вес."""
    return shelf.process(pkt(w, sec=0), repo)


def alert_types(repo):
    return [a.type for a in repo.list_alerts(severity=None, limit=100)]


def test_first_measurement_is_baseline(repo):
    assert start(repo) == {'status': 'BASELINE'}
    assert repo.get_shelf(SHELF).quantity == 10


def test_integer_removal(repo):
    start(repo)
    r = shelf.process(pkt(1600.0, sec=60), repo)
    assert r == {'status': 'SUCCESS', 'delta_items': -2, 'new_stock': 8}


def test_removal_within_tolerance(repo):
    start(repo)
    r = shelf.process(pkt(1605.0, sec=60), repo)
    assert r['status'] == 'SUCCESS'
    assert r['delta_items'] == -2
    assert r['new_stock'] == 8


def test_error_equals_tolerance_is_success(repo):
    start(repo)
    r = shelf.process(pkt(1594.0, sec=60), repo)  # ΔM = -406, Error = 6 г = ε
    assert r['status'] == 'SUCCESS'
    assert r['new_stock'] == 8


def test_weight_mismatch_anomaly(repo):
    start(repo)
    r = shelf.process(pkt(1720.0, sec=60), repo)  # ΔM = -280
    assert r['status'] == 'ANOMALY'
    assert r['reason'] == 'WEIGHT_MISMATCH'
    assert repo.get_shelf(SHELF).quantity == 10
    assert alert_types(repo) == ['WEIGHT_MISMATCH']


def test_noise_is_ignored(repo):
    start(repo)
    r = shelf.process(pkt(1998.5, sec=60), repo)
    assert r == {'status': 'NO_CHANGE'}
    assert repo.get_shelf(SHELF).quantity == 10


def test_restock(repo):
    start(repo)
    r = shelf.process(pkt(2200.0, sec=60), repo)
    assert r == {'status': 'SUCCESS', 'delta_items': 1, 'new_stock': 11}


def test_negative_stock_blocked(repo):
    start(repo, w=3000.0)
    r = shelf.process(pkt(600.0, sec=60), repo)  # снято 12 шт при остатке 10
    assert r['status'] == 'ANOMALY'
    assert r['reason'] == 'NEGATIVE_STOCK'
    assert repo.get_shelf(SHELF).quantity == 10
    assert alert_types(repo) == ['NEGATIVE_STOCK']


def test_duplicate_packet(repo):
    start(repo)
    with pytest.raises(DuplicatePacket):
        shelf.process(pkt(2000.0, sec=0), repo)


def test_unknown_shelf(repo):
    with pytest.raises(UnknownShelf):
        shelf.process(pkt(100.0, shelf_id='X9-9-9'), repo)
    assert alert_types(repo) == ['UNKNOWN_SHELF']


def test_new_baseline_after_anomaly(repo):
    start(repo)
    shelf.process(pkt(1720.0, sec=60), repo)             # аномалия
    r = shelf.process(pkt(1720.0, sec=120), repo)        # тот же вес
    assert r == {'status': 'NO_CHANGE'}
    assert alert_types(repo) == ['WEIGHT_MISMATCH']      # второго алерта нет