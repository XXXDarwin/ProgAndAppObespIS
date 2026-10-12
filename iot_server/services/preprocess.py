# iot_server/services/preprocess.py
from collections import deque

from config import PERIOD_S, TIMEOUT_PERIODS, WINDOW

buffers = {}  # буфер принятых отсчётов по зонам


def smooth(repo, p):
    buf = buffers.setdefault(p.zone, deque(maxlen=WINDOW))
    if buf and (p.timestamp - buf[-1][0]).total_seconds() > TIMEOUT_PERIODS * PERIOD_S:
        repo.add_alert('SENSOR_TIMEOUT', 'MEDIUM', p.zone, 'Пропуск отсчётов')
    buf.append((p.timestamp, p.temperature, p.humidity))
    n = len(buf)
    return sum(x[1] for x in buf) / n, sum(x[2] for x in buf) / n