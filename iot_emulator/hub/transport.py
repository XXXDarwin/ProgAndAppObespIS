import json
import urllib.error
import urllib.request


class TransportError(Exception):
    '''Нет связи с сервером (отказ в соединении, таймаут).'''


class HttpTransport:
    '''Реальная отправка на сервер ЛР №2. Возвращает HTTP-код.'''

    def __init__(self, base_url, timeout=3.0):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    def send(self, kind, packet, device_id, seq):
        req = urllib.request.Request(
            f'{self.base_url}/{kind}',
            data=json.dumps(packet).encode('utf-8'),
            method='POST',
            headers={'Content-Type': 'application/json',
                     'X-Device-Id': device_id,
                     'X-Seq': str(seq)})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code                      # 404, 409, 422 - ответ сервера
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