import random
import statistics
from pathlib import Path

from environment import Environment, ShelfModel
from sensors.climate import ClimateSensor
from sensors.weight import WeightSensor
from settings import load_config

WEIGHT_SAMPLES = 80        # 8 с при 10 Гц
REMOVE_AT = 20             # отсчёт, на котором снимают 2 шт (t = 2,0 с)


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
    for k in range(WEIGHT_SAMPLES):
        t = k * dt
        if k == REMOVE_AT:
            shelf.remove_items(2, t)
        rows.append((t, shelf.true_weight(t), sensor.read(t)))
    return rows, shelf


def hub_filter(rows, hub_cfg):
    '''Те же правила, что в IoTHub.poll_weight: медиана окна, устоявшееся значение,
    отправка по изменению. Возвращает (медианы, отсчёты отправки).'''
    n = hub_cfg['window']
    window, filtered, sent = [], [], []
    last = None
    for i, (_, _, w) in enumerate(rows):
        window = (window + [w])[-n:]
        if len(window) < n:
            filtered.append(None)
            continue
        med = statistics.median(window)
        filtered.append(med)
        if max(window) - min(window) > hub_cfg['stable_g']:
            continue
        if last is None or abs(med - last) > hub_cfg['delta_g']:
            sent.append(i)
            last = med
    return filtered, sent


def save_plots(climate, weight, shelf, filtered, sent):
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

    t_end = weight[-1][0]
    grid = [i * 0.01 for i in range(int(t_end * 100) + 1)]
    ax.cla()
    fig, ax = plt.subplots(figsize=(7.5, 3.5))
    ax.plot(grid, [shelf.true_weight(t) for t in grid], color='C0', lw=1, label='истинный')
    ax.plot([r[0] for r in weight], [r[2] for r in weight], 'o', ms=3, color='C1',
            label='измеренный (10 Гц)')
    pts = [(weight[i][0], f) for i, f in enumerate(filtered) if f is not None]
    ax.plot([p[0] for p in pts], [p[1] for p in pts], color='C2', lw=1.5,
            label='медиана окна хаба')
    ax.plot([weight[i][0] for i in sent], [filtered[i] for i in sent], 'k^', ms=8,
            label='отправка на сервер')
    ax.set_xlabel('Время, с')
    ax.set_ylabel('Вес, г')
    ax.set_title('Вес полки при снятии 2 шт')
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / 'weight.png', dpi=150)
    print('Графики сохранены в папку out/')


def main():
    cfg = load_config()
    rng = random.Random(cfg['seed'])
    climate = run_climate(cfg, rng)
    weight, shelf = run_weight(cfg, rng)
    filtered, sent = hub_filter(weight, cfg['hub'])
    print('t, с | T_ист | T_изм | H_изм')
    for t, t_true, t_meas, h_meas in climate[::5]:
        print(f'{t:5.0f} | {t_true:6.2f} | {t_meas:5.1f} | {h_meas:5.1f}')
    print('t, с | W_ист | W_изм | медиана')
    for i in range(18, 34):
        t, w_true, w_meas = weight[i]
        f = filtered[i]
        print(f'{t:5.1f} | {w_true:7.1f} | {w_meas:7.1f} | '
              f'{"" if f is None else format(f, "7.1f")}')
    print('Отправка хабом (t, с, вес, г):',
          [(round(weight[i][0], 1), filtered[i]) for i in sent])
    save_plots(climate, weight, shelf, filtered, sent)


if __name__ == '__main__':
    main()