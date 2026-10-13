from datetime import datetime, timezone

from hub.hub import IoTHub, OFFLINE, ONLINE
from hub.transport import TransportError

START = datetime(2026, 10, 8, 10, 0, 0, tzinfo=timezone.utc)
CFG = dict(window=5, stable_g=8.0, delta_g=5.0, heartbeat_s=60,
           backoff_min_s=1, backoff_max_s=30)


class FakeTransport:
    def __init__(self):
        self.online = True
        self.status = 200
        self.calls = []
        self.delivered = []

    def send(self, kind, packet, device_id, seq):
        self.calls.append(seq)
        if not self.online:
            raise TransportError('offline')
        if self.status in (200, 409):
            self.delivered.append((kind, packet, seq))
        return self.status


class ListSensor:
    def __init__(self, values):
        self.it = iter(values)

    def read(self, t):
        return next(self.it)


def make_hub():
    tr = FakeTransport()
    return IoTHub(tr, CFG, START), tr


def feed(hub, values, sid='A1-1-1', t0=0.0, step=1.0):
    s = ListSensor(values)
    for i in range(len(values)):
        hub.poll_weight(sid, s, t0 + i * step)


def shelf_weights(hub):
    return [p['weight_g'] for k, p, _ in hub.buffer if k == 'shelf']


def test_iso_format():
    hub, _ = make_hub()
    assert hub.iso(0) == '2026-10-08T10:00:00.000Z'
    assert hub.iso(65.1) == '2026-10-08T10:01:05.100Z'


def test_weight_waits_for_full_window():
    hub, _ = make_hub()
    feed(hub, [4000.0] * 4)
    assert len(hub.buffer) == 0


def test_weight_baseline_after_stable_window():
    hub, _ = make_hub()
    feed(hub, [4000.0] * 5)
    assert len(hub.buffer) == 1
    kind, pkt, seq = hub.buffer[0]
    assert kind == 'shelf' and pkt['shelf_id'] == 'A1-1-1' and pkt['weight_g'] == 4000.0
    assert seq == 1


def test_weight_sent_only_after_settling():
    hub, _ = make_hub()
    feed(hub, [4000.0] * 5 + [3600.0] * 5)
    assert shelf_weights(hub) == [4000.0, 3600.0]


def test_outlier_not_sent():
    hub, _ = make_hub()
    feed(hub, [4000.0] * 5 + [4090.0] + [4000.0] * 5)
    assert shelf_weights(hub) == [4000.0]


def test_small_change_below_delta_not_sent():
    hub, _ = make_hub()
    feed(hub, [4000.0] * 5 + [4003.0] * 5)
    assert shelf_weights(hub) == [4000.0]


def test_heartbeat_once_per_minute():
    hub, _ = make_hub()
    feed(hub, [4000.0] * 71)           # t = 0..70 с
    assert len(shelf_weights(hub)) == 2


def test_climate_sent_every_poll():
    hub, _ = make_hub()
    s = ListSensor([(22.5, 45.0), (22.6, 45.1)])
    hub.poll_climate(s, 'A', 0.0)
    hub.poll_climate(s, 'A', 5.0)
    assert [p['timestamp'] for _, p, _ in hub.buffer] == [
        '2026-10-08T10:00:00.000Z', '2026-10-08T10:00:05.000Z']
    assert hub.buffer[0][1]['zone'] == 'A'


def test_climate_dropout_makes_no_packet():
    hub, _ = make_hub()
    hub.poll_climate(ListSensor([None]), 'A', 0.0)
    assert len(hub.buffer) == 0 and hub.stats['sensor_faults'] == 1


def test_backoff_sequence():
    hub, tr = make_hub()
    tr.online = False
    hub.poll_climate(ListSensor([(22.5, 45.0)]), 'A', 0.0)
    t, waits = 0.0, []
    for _ in range(7):
        hub.flush(t)
        waits.append(hub.next_retry_t - t)
        t = hub.next_retry_t
    assert waits == [1, 2, 4, 8, 16, 30, 30]


def test_no_send_before_retry_time():
    hub, tr = make_hub()
    tr.online = False
    hub.poll_climate(ListSensor([(22.5, 45.0)]), 'A', 0.0)
    hub.flush(0.0)
    hub.flush(0.5)
    assert len(tr.calls) == 1
    hub.flush(1.0)
    assert len(tr.calls) == 2


def test_fifo_after_recovery_and_states():
    hub, tr = make_hub()
    tr.online = False
    s = ListSensor([(22.0, 45.0), (22.1, 45.0), (22.2, 45.0)])
    for i in range(3):
        hub.poll_climate(s, 'A', i * 5.0)
        hub.flush(i * 5.0)
    assert hub.state == OFFLINE and len(hub.buffer) == 3
    tr.online = True
    hub.flush(1000.0)
    assert [seq for _, _, seq in tr.delivered] == [1, 2, 3]
    assert len(hub.buffer) == 0 and hub.state == ONLINE


def test_409_is_success_and_422_is_dropped():
    hub, tr = make_hub()
    s = ListSensor([(22.0, 45.0), (22.1, 45.0)])
    hub.poll_climate(s, 'A', 0.0)
    tr.status = 409
    hub.flush(0.0)
    assert len(hub.buffer) == 0 and hub.stats['sent'] == 1
    hub.poll_climate(s, 'A', 5.0)
    tr.status = 422
    hub.flush(5.0)
    assert len(hub.buffer) == 0 and hub.stats['dropped'] == 1


def test_500_is_retried():
    hub, tr = make_hub()
    hub.poll_climate(ListSensor([(22.0, 45.0)]), 'A', 0.0)
    tr.status = 500
    hub.flush(0.0)
    assert len(hub.buffer) == 1 and hub.state == OFFLINE