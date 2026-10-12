# iot_server/services/shelf.py
from config import ACCEPT_NEW_BASELINE, NOISE_G, TOL_K, TOL_MIN_G
from services.errors import DuplicatePacket, UnknownShelf

EPS_FLOAT = 1e-9  # защита от ошибки округления float на границе допуска


def process(p, repo):
    s = repo.get_shelf(p.shelf_id)
    if s is None:
        repo.add_alert('UNKNOWN_SHELF', 'HIGH', p.shelf_id, 'Неизвестная полка')
        raise UnknownShelf(p.shelf_id)
    if not repo.register_packet(p.shelf_id, p.timestamp):
        raise DuplicatePacket()
    repo.save_measurement('shelf', p)
    if s.last_weight_g is None:
        s.last_weight_g = p.weight_g
        return {'status': 'BASELINE'}
    dm = p.weight_g - s.last_weight_g
    if abs(dm) <= NOISE_G:
        return {'status': 'NO_CHANGE'}
    n_raw = abs(dm) / s.unit_weight_g
    n = round(n_raw)
    error = abs(n_raw - n) * s.unit_weight_g
    eps = max(TOL_K * s.unit_weight_g, TOL_MIN_G)
    if n >= 1 and error <= eps + EPS_FLOAT:
        delta = n if dm > 0 else -n
        if s.quantity + delta < 0:
            repo.add_alert('NEGATIVE_STOCK', 'HIGH', p.shelf_id, 'Остаток ниже нуля')
            return {'status': 'ANOMALY', 'reason': 'NEGATIVE_STOCK'}
        s.quantity += delta
        s.last_weight_g = p.weight_g
        return {'status': 'SUCCESS', 'delta_items': delta, 'new_stock': s.quantity}
    repo.add_alert('WEIGHT_MISMATCH', 'HIGH', p.shelf_id,
                   f'ΔM={dm:.1f} г, ошибка {error:.1f} г')
    if ACCEPT_NEW_BASELINE:
        s.last_weight_g = p.weight_g
    return {'status': 'ANOMALY', 'reason': 'WEIGHT_MISMATCH',
            'error_g': round(error, 1), 'tolerance_g': round(eps, 1)}