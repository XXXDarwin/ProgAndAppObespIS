# iot_emulator/tests/test_quantize.py
import math
import random
import statistics

from sensors.quantize import quantize


def test_quantize_step_01():
    assert quantize(22.34, 0.1) == 22.3
    assert quantize(22.36, 0.1) == 22.4


def test_quantize_step_05():
    assert quantize(1000.3, 0.5) == 1000.5
    assert quantize(1000.2, 0.5) == 1000.0


def test_quantize_error_not_more_than_half_step():
    rng = random.Random(1)
    for step in (0.1, 0.5):
        for _ in range(2000):
            x = rng.uniform(0, 100)
            assert abs(quantize(x, step) - x) <= step / 2 + 1e-9


def test_quantize_sigma():
    rng = random.Random(1)
    xs = [rng.uniform(0, 100) for _ in range(20000)]
    errors = [quantize(x, 0.1) - x for x in xs]
    assert abs(statistics.pstdev(errors) - 0.1 / math.sqrt(12)) < 0.002