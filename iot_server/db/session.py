import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _load_env():
    path = Path(__file__).resolve().parent.parent / '.env'
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())


def get_url():
    _load_env()
    url = os.environ.get('IOT_DATABASE_URL')
    if url:
        return url
    pwd = os.environ.get('DB_PASSWORD', 'iot')
    port = os.environ.get('DB_PORT', '5433')
    return f'postgresql+psycopg2://iot:{pwd}@localhost:{port}/iot'


def make_session_factory(url=None):
    engine = create_engine(url or get_url())
    return sessionmaker(bind=engine, expire_on_commit=False)