import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


class TransportError(Exception):
    '''Нет связи с сервером (отказ в соединении, таймаут).'''


def _secret_from_env():
    raw = os.environ.get('IOT_HUB_SECRET')
    return bytes.fromhex(raw) if raw else None


class HttpTransport:
    '''Реальная отправка на сервер ЛР №2. Возвращает HTTP-код.
    Если задан секрет хаба (аргумент или IOT_HUB_SECRET), пакеты подписываются.'''

    def __init__(self, base_url, timeout=3.0, secret=None):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.secret = secret if secret is not None else _secret_from_env()
        # seq на проводе = старт в мс + номер: не сбрасывается после перезапуска
        self._seq_base = int(time.time() * 1000)

    def send(self, kind, packet, device_id, seq):
        data = json.dumps(packet).encode('utf-8')
        headers = {'Content-Type': 'application/json',
                   'X-Device-Id': device_id,
                   'X-Seq': str(seq)}
        if self.secret:
            wire_seq = self._seq_base + seq
            ts = datetime.now(timezone.utc).isoformat(timespec='seconds')
            msg = data + b'|' + ts.encode() + b'|' + str(wire_seq).encode()
            headers['X-Seq'] = str(wire_seq)
            headers['X-Timestamp'] = ts
            headers['X-Signature'] = hmac.new(self.secret, msg,
                                              hashlib.sha256).hexdigest()
        req = urllib.request.Request(f'{self.base_url}/{kind}', data=data,
                                     method='POST', headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code                      # 404, 409, 422, 401 - ответ сервера
        except (urllib.error.URLError, OSError) as e:
            raise TransportError(str(e)) from e


class DryRunTransport:
    '''Сервер не нужен: пакеты запоминаются и пишутся в файл (JSON Lines).'''

    def __init__(self, path=None, echo=False):
        self.path = path
        self.echo = echo
        self.records = []

    def send(self, kind, packet, device_id, seq):
        rec = {'kind': kind, 'seq': seq, 'device_id': device_id, 'packet': packet}
        self.records.append(rec)
        if self.echo:
            print(json.dumps(rec, ensure_ascii=False))
        if self.path:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        return 200


class FlakyTransport:
    '''Обёртка для сценария network_loss: пока online = False, связи нет.'''

    def __init__(self, inner):
        self.inner = inner
        self.online = True

    def send(self, kind, packet, device_id, seq):
        if not self.online:
            raise TransportError('сервер недоступен')
        return self.inner.send(kind, packet, device_id, seq)