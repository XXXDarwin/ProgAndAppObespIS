# iot_emulator/demo_sensors.py
import random
from pathlib import Path

from environment import Environment, ShelfModel
from sensors.climate import ClimateSensor
from sensors.weight import WeightSensor
from settings import load_config


def run_climate(cfg, rng):
    dt = 1 / cfg['climate']['fs_hz']
    env = Environment.from_config(cfg)
    sensor = ClimateSensor.from_config(env, rng, cfg)
    rows = []
    for k in range(60):
        t = k * dt
        if k == 20:
            env.set_target(28.0)
        env.update(dt)
        t_meas, h_meas = sensor.read(t)
        rows.append((t, env.temperature_at(t), t_meas, h_meas))
    return rows


def run_weight(cfg, rng):
    dt = 1 / cfg['weight']['fs_hz']
    shelf = ShelfModel.from_config(cfg, 'A1-1-1', unit_weight_g=200.0, items=10)
    sensor = WeightSensor.from_config(shelf, rng, cfg)
    rows = []
    for k in range(60):
        t = k * dt
        if k == 20:
            shelf.remove_items(2, t)
        rows.append((t, shelf.true_weight(t), sensor.read(t)))
    return rows, shelf


def save_plots(climate, weight, shelf):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('matplotlib не установлен, графики пропущены')
        return
    out = Path(__file__).with_name('out')
    out.mkdir(exist_ok=True)

    fig, ax = plt.subplots(figsize=(7.5, 3.5))
    ax.plot([r[0] for r in climate], [r[1] for r in climate], label='истинная')
    ax.plot([r[0] for r in climate], [r[2] for r in climate], 'o', ms=3, label='измеренная')
    ax.set_xlabel('Время, с')
    ax.set_ylabel('Температура, °C')
    ax.set_title('Температура зоны')
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / 'temperature.png', dpi=150)

    fig, ax = plt.subplots(figsize=(7.5, 3.5))
    grid = [i * 0.01 for i in range(6000)]
    ax.plot(grid, [shelf.true_weight(t) for t in grid], label='истинный')
    ax.plot([r[0] for r in weight], [r[2] for r in weight], 'o', ms=3, label='измеренный (1 Гц)')
    ax.set_xlabel('Время, с')
    ax.set_ylabel('Вес, г')
    ax.set_title('Вес полки при снятии 2 шт')
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / 'weight.png', dpi=150)
    print('Графики сохранены в папку out/')


def main():
    cfg = load_config()
    rng = random.Random(cfg['seed'])
    climate = run_climate(cfg, rng)
    weight, shelf = run_weight(cfg, rng)
    print('t, с | T_ист | T_изм | H_изм')
    for t, t_true, t_meas, h_meas in climate[::5]:
        print(f'{t:5.0f} | {t_true:6.2f} | {t_meas:5.1f} | {h_meas:5.1f}')
    print('t, с | W_ист | W_изм')
    for t, w_true, w_meas in weight[18:26]:
        print(f'{t:5.0f} | {w_true:7.1f} | {w_meas:7.1f}')
    save_plots(climate, weight, shelf)


if __name__ == '__main__':
    main()