import pytest
from pydantic import ValidationError

from schemas.telemetry import ClimatePacket, ShelfPacket

TS = '2026-10-08T10:00:00Z'


def climate(**kw):
    data = {'zone': 'A', 'temperature': 22.5, 'humidity': 45.0, 'timestamp': TS}
    data.update(kw)
    return ClimatePacket(**data)


def shelf(**kw):
    data = {'shelf_id': 'A1-1-1', 'weight_g': 4850.0, 'timestamp': TS}
    data.update(kw)
    return ShelfPacket(**data)


def test_valid_packets():
    assert climate().temperature == 22.5
    assert shelf().weight_g == 4850.0


@pytest.mark.parametrize('field,value', [
    ('temperature', 'hello'),
    ('temperature', -41),
    ('temperature', 86),
    ('humidity', -1),
    ('humidity', 101),
    ('zone', 'AB'),
    ('zone', 'a'),
])
def test_climate_invalid(field, value):
    with pytest.raises(ValidationError):
        climate(**{field: value})


def test_climate_missing_field():
    with pytest.raises(ValidationError):
        ClimatePacket(zone='A', temperature=22.5, timestamp=TS)


def test_climate_boundaries_ok():
    assert climate(temperature=-40, humidity=0).temperature == -40
    assert climate(temperature=85, humidity=100).humidity == 100


@pytest.mark.parametrize('field,value', [
    ('weight_g', -0.1),
    ('weight_g', 'heavy'),
    ('shelf_id', 'A1-1'),
    ('shelf_id', 'xx'),
])
def test_shelf_invalid(field, value):
    with pytest.raises(ValidationError):
        shelf(**{field: value})


def test_shelf_missing_field():
    with pytest.raises(ValidationError):
        ShelfPacket(shelf_id='A1-1-1', weight_g=100.0)