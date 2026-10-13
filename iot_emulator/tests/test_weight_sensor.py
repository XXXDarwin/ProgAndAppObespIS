# iot_emulator/tests/test_weight_sensor.py
import math
import random
import statistics

import pytest

from environment import ShelfModel
from sensors.weight import WeightSensor


def make_shelf(items=10, base_g=0.0):
    return ShelfModel('A1-1-1', unit_weight_g=200.0, items=items, base_g=base_g)


def test_noise_mean_and_sigma():
    s = WeightSensor(make_shelf(), random.Random(42))
    reads = [s.read(0) for _ in range(20000)]
    assert abs(statistics.fmean(reads) - 2000.0) < 0.1
    assert abs(statistics.pstdev(reads) - 1.5) < 0.05


def test_values_multiple_of_step():
    s = WeightSensor(make_shelf(), random.Random(42))
    for _ in range(1000):
        v = s.read(0)
        assert abs(v / 0.5 - round(v / 0.5)) < 1e-9


def test_zero_offset():
    s = WeightSensor(make_shelf(), random.Random(42), zero_offset_g=5.0)
    reads = [s.read(0) for _ in range(20000)]
    assert abs(statistics.fmean(reads) - 2005.0) < 0.1


def test_transient_settles():
    shelf = make_shelf()
    shelf.remove_items(2, t0=10.0)
    assert shelf.true_weight(9.0) == pytest.approx(2000.0)
    assert shelf.true_weight(10.0) == pytest.approx(2000.0)
    assert abs(shelf.true_weight(11.0) - 1600.0) < 1.0
    assert shelf.true_weight(13.0) == pytest.approx(1600.0, abs=0.01)


def test_transient_oscillates():
    shelf = make_shelf()
    shelf.remove_items(2, t0=10.0)
    # при cos = -1 вес «проскакивает» ниже конечного значения
    assert shelf.true_weight(10.0 + math.pi / 15.0) < 1600.0


def test_remove_fractional_items():
    shelf = make_shelf()
    shelf.remove_items(1.5, t0=5.0)
    assert shelf.true_weight(20.0) == pytest.approx(2000.0 - 300.0)


def test_add_items():
    shelf = make_shelf()
    shelf.remove_items(2, t0=5.0)
    shelf.add_items(2, t0=20.0)
    assert shelf.true_weight(40.0) == pytest.approx(2000.0, abs=0.01)


def test_remove_too_many_raises():
    shelf = make_shelf(items=3)
    with pytest.raises(ValueError):
        shelf.remove_items(4, t0=1.0)


def test_mean_after_step():
    shelf = make_shelf()
    shelf.remove_items(2, t0=10.0)
    s = WeightSensor(shelf, random.Random(7))
    reads = [s.read(15.0) for _ in range(2000)]
    assert abs(statistics.fmean(reads) - 1600.0) < 0.2


def test_never_negative():
    s = WeightSensor(make_shelf(items=0), random.Random(3))
    assert min(s.read(0) for _ in range(1000)) >= 0.0