from datetime import datetime, timezone

import pytest

from repositories.memory import MemoryRepository
from schemas.telemetry import ClimatePacket

TS = datetime(2026, 10, 8, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo():
    return MemoryRepository()


def test_seed(repo):
    zone = repo.get_zone('A')
    assert (zone.t_min, zone.t_max, zone.h_min, zone.h_max) == (18.0, 25.0, 40.0, 60.0)
    shelf = repo.get_shelf('A1-1-1')
    assert shelf.unit_weight_g == 200.0
    assert shelf.quantity == 10
    assert shelf.last_weight_g is None


def test_unknown_objects(repo):
    assert repo.get_zone('Z') is None
    assert repo.get_shelf('Z9-9-9') is None
    assert repo.get_status('A') is None


def test_status(repo):
    repo.set_status('A', 'WARNING')
    assert repo.get_status('A') == 'WARNING'
    assert repo.list_statuses() == {'A': 'WARNING'}


def test_duplicate_packet(repo):
    assert repo.register_packet('A1-1-1', TS) is True
    assert repo.register_packet('A1-1-1', TS) is False


def test_measurements_newest_first_and_limit(repo):
    for t in (20.0, 21.0, 22.0):
        repo.save_measurement('climate', ClimatePacket(
            zone='A', temperature=t, humidity=45.0, timestamp=TS))
    rows = repo.list_measurements(2)
    assert len(rows) == 2
    assert rows[0]['temperature'] == 22.0
    assert rows[0]['kind'] == 'climate'


def test_alerts_filter(repo):
    repo.add_alert('CLIMATE_WARNING', 'WARNING', 'A', 'x')
    repo.add_alert('WEIGHT_MISMATCH', 'HIGH', 'A1-1-1', 'y')
    assert len(repo.list_alerts(None, 50)) == 2
    high = repo.list_alerts('HIGH', 50)
    assert [a.type for a in high] == ['WEIGHT_MISMATCH']
    assert repo.list_alerts(None, 1)[0].type == 'WEIGHT_MISMATCH'