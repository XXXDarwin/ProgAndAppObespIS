from datetime import datetime, timezone

import config
from domain.models import Alert, Shelf, ZoneLimits
from repositories.base import Repository


class MemoryRepository(Repository):
    def __init__(self, seed=True):
        self._zones = {}
        self._shelves = {}
        self._status = {}
        self._packets = set()
        self._measurements = []
        self._alerts = []
        if seed:
            self._seed()

    def _seed(self):
        for zone, lim in config.SEED_ZONES.items():
            self._zones[zone] = ZoneLimits(zone=zone, **lim)
        for shelf_id, s in config.SEED_SHELVES.items():
            self._shelves[shelf_id] = Shelf(
                shelf_id=shelf_id, zone=s['zone'], product_name=s['product'],
                unit_weight_g=s['unit_weight_g'], quantity=s['quantity'])

    def get_zone(self, zone):
        return self._zones.get(zone)

    def get_status(self, zone):
        return self._status.get(zone)

    def set_status(self, zone, status):
        self._status[zone] = status

    def list_statuses(self):
        return dict(self._status)

    def get_shelf(self, shelf_id):
        return self._shelves.get(shelf_id)

    def list_shelves(self):
        return list(self._shelves.values())

    def register_packet(self, shelf_id, ts):
        key = (shelf_id, ts)
        if key in self._packets:
            return False
        self._packets.add(key)
        return True

    def save_measurement(self, kind, packet):
        row = {'kind': kind}
        row.update(packet.model_dump(mode='json'))
        self._measurements.append(row)

    def list_measurements(self, limit):
        return list(reversed(self._measurements))[:limit]

    def add_alert(self, type_, severity, source, details):
        alert = Alert(id=len(self._alerts) + 1, type=type_, severity=severity,
                      source=source, details=details,
                      created=datetime.now(timezone.utc))
        self._alerts.append(alert)
        return alert

    def list_alerts(self, severity=None, limit=50):
        rows = [a for a in reversed(self._alerts)
                if severity is None or a.severity == severity]
        return rows[:limit]