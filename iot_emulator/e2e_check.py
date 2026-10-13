import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from hub.transport import HttpTransport
from runner import load_scenario, run
from settings import load_config

ROOT = Path(__file__).resolve().parent
SERVER_DIR = ROOT.parent / 'iot_server'
OUT = ROOT / 'out'
PORT = 8000
BASE = f'http://127.0.0.1:{PORT}'
NAMES = ['normal', 'overheat', 'pick_items', 'anomaly', 'network_loss', 'sensor_fault']

# Ожидания из ЛР №3, табл. 9 (это ожидания, а не результаты)
EXPECT = {
    'normal': 'статус NORMAL, алертов нет',
    'overheat': 'CLIMATE_WARNING и CLIMATE_CRITICAL по одному, статус зоны A: CRITICAL',
    'pick_items': 'остаток A1-1-1: 10 -> 8 -> 9, алертов веса нет',
    'anomaly': 'один WEIGHT_MISMATCH, остаток A1-1-1 = 10',
    'network_loss': 'в буфере 0, пакеты доставлены по порядку, дублей нет',
    'sensor_fault': 'один SENSOR_TIMEOUT, выброс и залипание алертов не дают',
}


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return json.loads(r.read().decode('utf-8'))


def server_alive():
    try:
        get('/health')
        return True
    except Exception:
        return False


def start_server(name):
    OUT.mkdir(exist_ok=True)
    log = open(OUT / f'server_{name}.log', 'w', encoding='utf-8')
    proc = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'main:app', '--port', str(PORT)],
        cwd=SERVER_DIR, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(60):
        if server_alive():
            return proc, log
        time.sleep(0.25)
    proc.terminate()
    raise RuntimeError('сервер не запустился, смотри out/server_' + name + '.log')


def stop_server(proc, log):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()


def run_one(name, cfg, report):
    proc, log = start_server(name)
    lines = []
    try:
        transport = HttpTransport(BASE + '/api/v1/telemetry')
        hub = run(cfg, load_scenario(name), transport,
                  start=datetime.now(timezone.utc), speed=0, log=lines.append)
        alerts = get('/api/v1/alerts?limit=100')
        inventory = get('/api/v1/inventory')
        status = get('/api/v1/climate/status')
    finally:
        stop_server(proc, log)

    def out(s=''):
        print(s)
        report.append(s)

    out('=' * 70)
    out(f'СЦЕНАРИЙ: {name}')
    out(f'Ожидалось: {EXPECT[name]}')
    out(f'Хаб: отправлено {hub.stats["sent"]}, отброшено {hub.stats["dropped"]}, '
        f'сбоев датчиков {hub.stats["sensor_faults"]}, сбоев связи {hub.stats["failures"]}, '
        f'в буфере {len(hub.buffer)}')
    if name == 'network_loss':
        out('Журнал хаба:')
        for ln in lines[:15]:
            out('  ' + ln)
    out('GET /climate/status:')
    out('  ' + json.dumps(status, ensure_ascii=False))
    out('GET /inventory:')
    out('  ' + json.dumps(inventory, ensure_ascii=False))
    out('GET /alerts:')
    out('  ' + json.dumps(alerts, ensure_ascii=False))


def main():
    names = sys.argv[1:] or NAMES
    bad = [n for n in names if n not in NAMES]
    if bad:
        sys.exit(f'неизвестный сценарий: {bad}; доступны: {NAMES}')
    if server_alive():
        sys.exit(f'порт {PORT} занят (WMS или старый uvicorn): останови его и повтори')
    cfg = load_config()
    report = []
    for n in names:
        run_one(n, cfg, report)
    path = OUT / 'e2e_report.txt'
    path.write_text('\n'.join(report), encoding='utf-8')
    print(f'\nОтчёт сохранён: {path}')


if __name__ == '__main__':
    main()