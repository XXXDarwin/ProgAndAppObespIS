# iot_emulator/settings.py
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).with_name('config.yaml')


def load_config(path=None):
    with open(path or DEFAULT_PATH, encoding='utf-8') as f:
        return yaml.safe_load(f)