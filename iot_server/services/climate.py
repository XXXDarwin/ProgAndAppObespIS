from config import CRIT_H, CRIT_T
from services.errors import UnknownZone
from services.preprocess import smooth

RANK = {'NORMAL': 0, 'WARNING': 1, 'CRITICAL': 2}


def evaluate(z, t, h):
    level, reasons = 'NORMAL', []
    checks = (('Температура', t, z.t_min, z.t_max, CRIT_T),
              ('Влажность', h, z.h_min, z.h_max, CRIT_H))
    for name, v, lo, hi, margin in checks:
        if lo <= v <= hi:
            continue
        sev = 'CRITICAL' if (v < lo - margin or v > hi + margin) else 'WARNING'
        reasons.append(f'{name} {v:.1f} вне диапазона {lo}–{hi}')
        level = max(level, sev, key=RANK.get)
    return level, reasons


def process(p, repo):
    zone = repo.get_zone(p.zone)
    if zone is None:
        raise UnknownZone(p.zone)
    level, reasons = evaluate(zone, *smooth(repo, p))
    prev = repo.get_status(p.zone)
    repo.save_measurement('climate', p)
    repo.set_status(p.zone, level)
    if RANK[level] > RANK[prev or 'NORMAL']:
        repo.add_alert('CLIMATE_' + level, level, p.zone, '; '.join(reasons))
    return {'status': level, 'reasons': reasons}