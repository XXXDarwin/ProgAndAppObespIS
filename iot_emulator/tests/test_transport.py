import pytest

from hub.transport import DryRunTransport, FlakyTransport, HttpTransport, TransportError


def test_dryrun_records_and_returns_200():
    tr = DryRunTransport()
    assert tr.send('climate', {'zone': 'A'}, 'HUB-01', 1) == 200
    assert tr.records[0]['seq'] == 1 and tr.records[0]['kind'] == 'climate'


def test_dryrun_writes_file(tmp_path):
    p = tmp_path / 'out.jsonl'
    tr = DryRunTransport(path=str(p))
    tr.send('shelf', {'shelf_id': 'A1-1-1'}, 'HUB-01', 1)
    tr.send('shelf', {'shelf_id': 'A1-1-1'}, 'HUB-01', 2)
    assert len(p.read_text(encoding='utf-8').strip().splitlines()) == 2


def test_flaky_offline_raises():
    tr = FlakyTransport(DryRunTransport())
    tr.online = False
    with pytest.raises(TransportError):
        tr.send('climate', {}, 'HUB-01', 1)
    tr.online = True
    assert tr.send('climate', {}, 'HUB-01', 1) == 200


def test_http_refused_is_transport_error():
    tr = HttpTransport('http://127.0.0.1:9/api', timeout=0.5)
    with pytest.raises(TransportError):
        tr.send('climate', {}, 'HUB-01', 1)