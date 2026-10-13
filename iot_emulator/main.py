import argparse
from datetime import datetime
from pathlib import Path

from hub.transport import DryRunTransport, HttpTransport
from runner import load_scenario, run
from settings import load_config


def main():
    ap = argparse.ArgumentParser(description='Эмулятор IoT-Хаба')
    ap.add_argument('scenario', help='normal, overheat, pick_items, anomaly, network_loss, sensor_fault')
    ap.add_argument('--mode', choices=('dry-run', 'real'), default='dry-run')
    ap.add_argument('--speed', type=float, default=1.0, help='1 - реальное время, 10 - x10, 0 - без пауз')
    ap.add_argument('--server', help='адрес сервера (по умолчанию из config.yaml)')
    ap.add_argument('--out', default='out/dry_run.jsonl', help='файл для dry-run')
    ap.add_argument('--start', help='начало модельного времени, ISO 8601 (по умолчанию сейчас)')
    a = ap.parse_args()

    cfg = load_config()
    if a.mode == 'real':
        transport = HttpTransport(a.server or cfg['hub']['server_url'])
    else:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.unlink(missing_ok=True)
        transport = DryRunTransport(path=str(out))
    start = datetime.fromisoformat(a.start.replace('Z', '+00:00')) if a.start else None

    hub = run(cfg, load_scenario(a.scenario), transport, start=start,
              speed=a.speed, log=print)
    print(f'Готово: отправлено {hub.stats["sent"]}, отброшено {hub.stats["dropped"]}, '
          f'сбоев датчиков {hub.stats["sensor_faults"]}, в буфере {len(hub.buffer)}')


if __name__ == '__main__':
    main()