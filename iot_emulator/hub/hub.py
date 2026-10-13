import statistics
from collections import deque
from datetime import timedelta

from hub.transport import TransportError

ONLINE = 'ONLINE'
OFFLINE = 'OFFLINE'
RECOVERY = 'RECOVERY'

DONE_CODES = (200, 409)    # доставлено; 409 - дубликат, считаем успехом
DROP_CODES = (404, 422)    # ошибка данных, повторять бессмысленно


class IoTHub:
    '''Модель IoT-Хаба: опрос, фильтр, пакет, буфер FIFO, отправка с повторами.
    Время модельное (секунды от старта), поэтому ускорение ничего не ломает.'''

    def __init__(self, transport, cfg, start, device_id='HUB-01', log=None):
        self.transport = transport
        self.window_n = cfg['window']
        self.stable_g = cfg['stable_g']
        self.delta_g = cfg['delta_g']
        self.heartbeat_s = cfg['heartbeat_s']
        self.backoff_min = cfg['backoff_min_s']
        self.backoff_max = cfg['backoff_max_s']
        self.start = start                     # datetime с tz=UTC
        self.device_id = device_id
        self.log = log or (lambda msg: None)
        self.buffer = deque()                  # (kind, packet, seq)
        self.seq = 0
        self.state = ONLINE
        self.backoff_s = self.backoff_min
        self.next_retry_t = 0.0
        self.windows = {}                      # shelf_id -> окно отсчётов
        self.last_sent = {}                    # shelf_id -> последний отправленный вес
        self.last_t = {}                       # shelf_id -> время последней отправки
        self.stats = {'sent': 0, 'dropped': 0, 'sensor_faults': 0, 'failures': 0}

    def iso(self, t):
        ts = self.start + timedelta(seconds=round(t, 3))
        return ts.isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    def _log(self, t, msg):
        self.log(f't={t:7.1f} с  {msg}')

    def _enqueue(self, kind, packet):
        self.seq += 1
        self.buffer.append((kind, packet, self.seq))

    # ---------- опрос датчиков ----------

    def poll_climate(self, sensor, zone, t):
        '''Климат уходит на сервер каждый период опроса (иначе будет ложный SENSOR_TIMEOUT).'''
        r = sensor.read(t)
        if r is None:
            self.stats['sensor_faults'] += 1
            self._log(t, f'датчик климата зоны {zone} не ответил, пакет не формируется')
            return
        temperature, humidity = r
        self._enqueue('climate', {'zone': zone, 'temperature': temperature,
                                  'humidity': humidity, 'timestamp': self.iso(t)})

    def poll_weight(self, shelf_id, sensor, t):
        '''Медиана окна; отправка только устоявшегося значения, по изменению или heartbeat.'''
        w = sensor.read(t)
        if w is None:
            self.stats['sensor_faults'] += 1
            return
        win = self.windows.setdefault(shelf_id, deque(maxlen=self.window_n))
        win.append(w)
        if len(win) < self.window_n or max(win) - min(win) > self.stable_g:
            return                             # окно не заполнено или показания колеблются
        med = statistics.median(win)
        last = self.last_sent.get(shelf_id)
        due = last is None or t - self.last_t[shelf_id] >= self.heartbeat_s
        if due or abs(med - last) > self.delta_g:
            self._enqueue('shelf', {'shelf_id': shelf_id, 'weight_g': med,
                                    'timestamp': self.iso(t)})
            self.last_sent[shelf_id] = med
            self.last_t[shelf_id] = t

    # ---------- отправка ----------

    def _fail(self, t, reason):
        self.stats['failures'] += 1
        self.next_retry_t = t + self.backoff_s
        self._log(t, f'{reason}; повтор через {self.backoff_s} с, в буфере {len(self.buffer)}')
        self.backoff_s = min(self.backoff_s * 2, self.backoff_max)
        self.state = OFFLINE

    def flush(self, t):
        while self.buffer:
            if t < self.next_retry_t:
                return                         # ждём окончания паузы
            kind, pkt, seq = self.buffer[0]
            try:
                code = self.transport.send(kind, pkt, self.device_id, seq)
            except TransportError:
                self._fail(t, 'нет связи')
                return
            if code in DONE_CODES:
                self.buffer.popleft()
                self.stats['sent'] += 1
            elif code in DROP_CODES:
                self.buffer.popleft()
                self.stats['dropped'] += 1
                self._log(t, f'сервер ответил {code}, пакет {kind} #{seq} отброшен')
            else:
                self._fail(t, f'ответ сервера {code}')
                return
            self.backoff_s = self.backoff_min
            self.next_retry_t = 0.0
            if self.state == OFFLINE:
                self.state = RECOVERY
                self._log(t, 'связь восстановлена, отправка накопленного')
        if self.state != ONLINE:
            self.state = ONLINE
            self._log(t, 'буфер пуст')