import hashlib
import hmac
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from hub.transport import HttpTransport

SECRET = bytes.fromhex('aa' * 32)


class Capture(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        Capture.seen.append((self.headers, body))
        self.send_response(200)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def server(monkeypatch):
    monkeypatch.delenv('IOT_HUB_SECRET', raising=False)
    Capture.seen = []
    srv = HTTPServer(('127.0.0.1', 0), Capture)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f'http://127.0.0.1:{srv.server_port}/api/v1/telemetry'
    srv.shutdown()
    srv.server_close()


def test_signed_request(server):
    tr = HttpTransport(server, secret=SECRET)
    assert tr.send('shelf', {'shelf_id': 'A1-1-1', 'weight_g': 2000.0,
                             'timestamp': '2026-10-08T10:00:00Z'}, 'HUB-01', 7) == 200
    h, body = Capture.seen[0]
    ts, seq = h['X-Timestamp'], h['X-Seq']
    expected = hmac.new(SECRET, body + b'|' + ts.encode() + b'|' + seq.encode(),
                        hashlib.sha256).hexdigest()
    assert h['X-Signature'] == expected
    assert h['X-Device-Id'] == 'HUB-01' and int(seq) > 10 ** 12


def test_unsigned_without_secret(server):
    tr = HttpTransport(server)
    tr.send('climate', {'zone': 'A'}, 'HUB-01', 7)
    h, _ = Capture.seen[0]
    assert h['X-Seq'] == '7' and h['X-Signature'] is None