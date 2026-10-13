from datetime import datetime, timezone

import pytest

from hub.transport import DryRunTransport
from runner import load_scenario, run
from settings import load_config

START = datetime(2026, 10, 8, 10, 0, 0, tzinfo=timezone.utc)
NAMES = ['normal', 'overheat', 'pick_items', 'anomaly', 'network_loss', 'sensor_fault']


def go(name):
    tr = DryRunTransport()
    hub = run(load_config(), load_scenario(name), tr, start=START)
    return hub, tr.records


def offset(rec):
    ts = datetime.fromisoformat(rec['packet']['timestamp'].replace('Z', '+00:00'))
    return (ts - START).total_seconds()


def weights(recs):
    return [r['packet']['weight_g'] for r in recs if r['kind'] == 'shelf']


def climate(recs):
    return [r for r in recs if r['kind'] == 'climate']


@pytest.mark.parametrize('name', NAMES)
def test_scenario_files_load(name):
    sc = load_scenario(name)
    assert sc['duration_s'] > 0 and sc['shelves']


def test_normal_counts():
    hub, recs = go('normal')
    assert len(climate(recs)) == 25                 # t = 0, 5, ..., 120
    assert 1 <= len(weights(recs)) <= 4             # baseline и heartbeat
    assert hub.stats['sent'] == len(recs) and len(hub.buffer) == 0


def test_reproducible():
    _, a = go('pick_items')
    _, b = go('pick_items')
    assert a == b


def test_overheat_reaches_high_temperature():
    _, recs = go('overheat')
    assert climate(recs)[-1]['packet']['temperature'] > 36


def test_pick_items_weights():
    _, recs = go('pick_items')
    ws = weights(recs)
    assert any(abs(w - 1600) <= 5 for w in ws)      # снято 2 шт
    assert any(abs(w - 1800) <= 5 for w in ws)      # возвращена 1 шт


def test_anomaly_weight():
    _, recs = go('anomaly')
    assert any(abs(w - 1700) <= 5 for w in weights(recs))   # снято 1,5 шт


def test_network_loss_order_and_no_duplicates():
    hub, recs = go('network_loss')
    assert len(hub.buffer) == 0
    seqs = [r['seq'] for r in recs]
    assert seqs == sorted(seqs)
    keys = [(r['kind'], r['packet']['timestamp']) for r in recs]
    assert len(keys) == len(set(keys))


def test_sensor_fault_gap_in_climate():
    hub, recs = go('sensor_fault')
    assert hub.stats['sensor_faults'] == 4          # t = 80, 85, 90, 95
    assert not [r for r in climate(recs) if 75 < offset(r) < 100]