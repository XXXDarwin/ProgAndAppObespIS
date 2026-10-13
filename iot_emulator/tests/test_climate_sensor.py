# iot_emulator/tests/test_climate_sensor.py
import random
import statistics

import pytest

from environment import Environment
from sensors.climate import ClimateSensor


def make(seed=42, t_start=22.0, humidity=45.0, **kw):
    env = Environment(t_start=t_start, humidity=humidity, amplitudes=(), frequencies=())
    return env, ClimateSensor(env, random.Random(seed), **kw)


def test_noise_mean_and_sigma():
    _, s = make()
    reads = [s.read(0) for _ in range(20000)]
    temps = [r[0] for r in reads]
    hums = [r[1] for r in reads]
    assert abs(statistics.fmean(temps) - 22.0) < 0.02
    assert abs(statistics.pstdev(temps) - 0.3) < 0.02
    assert abs(statistics.fmean(hums) - 45.0) < 0.05
    assert abs(statistics.pstdev(hums) - 1.0) < 0.05


def test_values_multiple_of_step():
    _, s = make()
    for _ in range(1000):
        t, h = s.read(0)
        assert abs(t / 0.1 - round(t / 0.1)) < 1e-6
        assert abs(h / 0.1 - round(h / 0.1)) < 1e-6


def test_dropout_returns_none():
    _, s = make()
    s.set_fault('dropout')
    assert s.read(0) is None
    s.set_fault(None)
    assert s.read(5) is not None


def test_stuck_repeats_last_value():
    env, s = make()
    first = s.read(0)
    s.set_fault('stuck')
    env.set_target(30.0)
    env.update(1000.0)
    assert s.read(5) == first
    assert s.read(10) == first


def test_outlier_is_one_shot():
    _, s = make()
    s.read(0)
    s.inject_outlier(8.5)
    spike = s.read(0)
    after = s.read(0)
    assert spike[0] - 22.0 > 7.0
    assert abs(after[0] - 22.0) < 2.0


def test_same_seed_is_reproducible():
    _, a = make(seed=42)
    _, b = make(seed=42)
    assert [a.read(k * 5) for k in range(50)] == [b.read(k * 5) for k in range(50)]


def test_values_clipped_to_contract_range():
    _, s = make(humidity=99.9, sigma_h=5.0)
    assert all(0 <= s.read(0)[1] <= 100 for _ in range(2000))
    _, s = make(humidity=0.1, sigma_h=5.0)
    assert all(0 <= s.read(0)[1] <= 100 for _ in range(2000))
    _, s = make(t_start=84.9, sigma_t=5.0)
    assert all(s.read(0)[0] <= 85 for _ in range(2000))


def test_drift():
    _, s = make(sigma_t=0.0, sigma_h=0.0, drift_per_h=3.6)
    assert s.read(0)[0] == pytest.approx(22.0)
    assert s.read(3600)[0] == pytest.approx(25.6)


def test_unknown_fault_rejected():
    _, s = make()
    with pytest.raises(ValueError):
        s.set_fault('explode')