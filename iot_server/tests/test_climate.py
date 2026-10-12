# iot_server/tests/test_climate.py
from datetime import datetime, timedelta, timezone

import pytest

from repositories.memory import MemoryRepository
from schemas.telemetry import ClimatePacket
from services import climate, preprocess
from services.errors import UnknownZone

T0 = datetime(2026, 10, 8, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clean_buffers():
    preprocess.buffers.clear()
    yield
    preprocess.buffers.clear()


@pytest.fixture
def repo():
    return MemoryRepository(seed=True)


def pkt(t, h=45.0, sec=0, zone='A'):
    return ClimatePacket(zone=zone, temperature=t, humidity=h,
                         timestamp=T0 + timedelta(seconds=sec))


def alert_types(repo):
    return [a.type for a in repo.list_alerts(severity=None, limit=100)]


def test_normal(repo):
    r = climate.process(pkt(22.5), repo)
    assert r['status'] == 'NORMAL'
    assert alert_types(repo) == []


def test_high_temperature_warning(repo):
    r = climate.process(pkt(28.0), repo)
    assert r['status'] == 'WARNING'
    assert alert_types(repo) == ['CLIMATE_WARNING']


def test_critical_temperature(repo):
    r = climate.process(pkt(40.0), repo)
    assert r['status'] == 'CRITICAL'
    assert alert_types(repo) == ['CLIMATE_CRITICAL']


def test_repeated_warning_single_alert(repo):
    climate.process(pkt(28.0, sec=0), repo)
    climate.process(pkt(28.0, sec=5), repo)
    assert alert_types(repo) == ['CLIMATE_WARNING']


def test_outlier_suppressed_by_moving_average(repo):
    for i in range(4):
        climate.process(pkt(22.5, sec=i * 5), repo)
    r = climate.process(pkt(31.0, sec=20), repo)
    assert r['status'] == 'NORMAL'
    assert alert_types(repo) == []


def test_boundary_25_is_normal(repo):
    assert climate.process(pkt(25.0), repo)['status'] == 'NORMAL'


def test_boundary_30_is_warning(repo):
    assert climate.process(pkt(30.0), repo)['status'] == 'WARNING'


def test_humidity_warning(repo):
    assert climate.process(pkt(22.5, h=65.0), repo)['status'] == 'WARNING'


def test_humidity_critical(repo):
    assert climate.process(pkt(22.5, h=75.0), repo)['status'] == 'CRITICAL'


def test_escalation_creates_second_alert(repo):
    climate.process(pkt(28.0, sec=0), repo)
    r = climate.process(pkt(40.0, sec=5), repo)
    assert r['status'] == 'CRITICAL'
    # list_alerts отдаёт записи от новых к старым
    assert alert_types(repo) == ['CLIMATE_CRITICAL', 'CLIMATE_WARNING']

def test_unknown_zone(repo):
    with pytest.raises(UnknownZone):
        climate.process(pkt(22.5, zone='Z'), repo)
    assert repo.list_measurements(10) == []


def test_sensor_timeout(repo):
    climate.process(pkt(22.5, sec=0), repo)
    climate.process(pkt(22.5, sec=20), repo)
    assert 'SENSOR_TIMEOUT' in alert_types(repo)


def test_no_timeout_at_exactly_three_periods(repo):
    climate.process(pkt(22.5, sec=0), repo)
    climate.process(pkt(22.5, sec=15), repo)
    assert 'SENSOR_TIMEOUT' not in alert_types(repo)


def test_measurement_and_status_saved(repo):
    climate.process(pkt(28.0), repo)
    assert len(repo.list_measurements(10)) == 1
    assert repo.get_status('A') == 'WARNING'