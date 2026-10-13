import copy
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from environment import Environment, ShelfModel
from hub.hub import IoTHub
from hub.transport import FlakyTransport
from sensors.climate import ClimateSensor
from sensors.weight import WeightSensor

SCENARIO_DIR = Path(__file__).parent / 'scenarios'


def load_scenario(name):
    with open(SCENARIO_DIR / f'{name}.yaml', encoding='utf-8') as f:
        return yaml.safe_load(f)


def run(cfg, scenario, transport, start=None, speed=0.0, log=None):
    '''Прогон сценария. speed: 1 - реальное время, 10 - x10, 0 - без пауз.'''
    cfg = copy.deepcopy(cfg)
    if 'tau_s' in scenario:                    # инерция среды для сценария
        cfg['climate']['tau_s'] = scenario['tau_s']
    rng = random.Random(scenario.get('seed', cfg.get('seed', 42)))
    start = start or datetime.now(timezone.utc)
    zone = scenario.get('zone', 'A')

    env = Environment.from_config(cfg)
    c, w = cfg['climate'], cfg['weight']
    csensor = ClimateSensor(env, rng, sigma_t=c['sigma_t'], sigma_h=c['sigma_h'],
                            step_t=c['step_t'], step_h=c['step_h'],
                            drift_per_h=c['drift_per_h'])
    shelves = {}
    for s in scenario['shelves']:
        model = ShelfModel.from_config(cfg, s['shelf_id'], s['unit_weight_g'], s['items'])
        shelves[s['shelf_id']] = (model, WeightSensor(
            model, rng, sigma_g=w['sigma_g'], step_g=w['step_g'],
            zero_offset_g=w['zero_offset_g']))

    net = FlakyTransport(transport)
    hub = IoTHub(net, cfg['hub'], start, device_id=cfg['hub'].get('device_id', 'HUB-01'),
                 log=log)

    def apply(ev):
        at = ev['at']
        if 'climate_target' in ev:
            env.set_target(ev['climate_target']['temperature'])
        elif 'climate_fault' in ev:
            mode = ev['climate_fault']['mode']
            csensor.set_fault(None if mode == 'none' else mode)
        elif 'climate_outlier' in ev:
            csensor.inject_outlier(delta_t=ev['climate_outlier'].get('delta_t', 8.5))
        elif 'shelf_remove' in ev:
            d = ev['shelf_remove']
            shelves[d['shelf_id']][0].remove_items(d['items'], at)
        elif 'shelf_add' in ev:
            d = ev['shelf_add']
            shelves[d['shelf_id']][0].add_items(d['items'], at)
        elif 'network' in ev:
            net.online = bool(ev['network']['online'])
            hub._log(at, 'СВЯЗЬ ЕСТЬ' if net.online else 'СВЯЗЬ ПОТЕРЯНА')
        else:
            raise ValueError(f'неизвестное событие сценария: {ev}')

    dt = 1.0 / w['fs_hz']                      # шаг опроса веса
    per_climate = round(cfg['hub']['climate_period_s'] / dt)
    steps = round(scenario['duration_s'] / dt)
    events = sorted(scenario.get('events', []), key=lambda e: e['at'])
    ei = 0
    t = 0.0
    for k in range(steps + 1):
        t = round(k * dt, 6)
        while ei < len(events) and events[ei]['at'] <= t:
            apply(events[ei])
            ei += 1
        if k % per_climate == 0:
            if k > 0:
                env.update(per_climate * dt)
            hub.poll_climate(csensor, zone, t)
        for sid, (_, sensor) in shelves.items():
            hub.poll_weight(sid, sensor, t)
        hub.flush(t)
        if speed > 0:
            time.sleep(dt / speed)
    return hub