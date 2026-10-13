# iot_emulator/tests/test_environment.py
import math

import pytest

from environment import Environment


def plain(**kw):
    return Environment(amplitudes=(), frequencies=(), **kw)


def test_inertia_one_step():
    env = plain(t_start=20.0, tau_s=100.0)
    env.set_target(30.0)
    env.update(100.0)
    assert env.t_base == pytest.approx(20.0 + (1 - math.exp(-1)) * 10.0)


def test_converges_to_target():
    env = plain(t_start=20.0, tau_s=100.0)
    env.set_target(30.0)
    for _ in range(100):
        env.update(10.0)
    assert abs(env.temperature_at(0) - 30.0) < 0.01


def test_harmonics_formula():
    env = Environment(t_start=22.0, amplitudes=(1.0,), frequencies=(0.01,))
    # sin(2*pi*0.01*25) = sin(pi/2) = 1
    assert env.temperature_at(25.0) == pytest.approx(23.0)


def test_harmonics_amplitude_bound():
    env = Environment(t_start=22.0)
    limit = sum(env.amplitudes) + 1e-9
    for k in range(500):
        assert abs(env.temperature_at(k * 5.0) - 22.0) <= limit


def test_nyquist_violation_rejected():
    with pytest.raises(ValueError):
        Environment(amplitudes=(1.0,), frequencies=(0.1,), fs_hz=0.2)
    with pytest.raises(ValueError):
        Environment(amplitudes=(1.0,), frequencies=(0.5,), fs_hz=0.2)
    Environment(amplitudes=(1.0,), frequencies=(0.09,), fs_hz=0.2)