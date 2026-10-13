# iot_emulator/tests/test_config.py
from environment import Environment, ShelfModel
from settings import load_config


def test_config_loads():
    cfg = load_config()
    assert cfg['seed'] == 42
    assert cfg['climate']['fs_hz'] == 0.2
    assert cfg['weight']['fs_hz'] == 1.0


def test_harmonics_below_nyquist():
    c = load_config()['climate']
    h = c['harmonics']
    assert len(h['amplitudes']) == len(h['frequencies_hz'])
    assert all(f < c['fs_hz'] / 2 for f in h['frequencies_hz'])


def test_objects_build_from_config():
    cfg = load_config()
    env = Environment.from_config(cfg)
    shelf = ShelfModel.from_config(cfg, 'A1-1-1', 200.0, 10)
    assert env.temperature_at(0) == 22.0
    assert shelf.true_weight(0) == 2000.0