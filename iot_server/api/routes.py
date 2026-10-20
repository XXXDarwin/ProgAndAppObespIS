# iot_server/api/routes.py
import os
from contextlib import contextmanager
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError

from api import auth
from repositories.memory import MemoryRepository
from repositories.sql import SqlRepository, UnknownSensor
from schemas.telemetry import ClimatePacket, ShelfPacket
from services import climate, shelf
from services.errors import DuplicatePacket, UnknownShelf, UnknownZone

router = APIRouter()
repo = MemoryRepository(seed=True)  # режим по умолчанию (память, ЛР №2)
_session_factory = None             # не None: режим SQL (ЛР №4)
_auth_enabled = False               # True: пакеты должны быть подписаны (ЛР №4)


def use_sql(factory=None):
    global _session_factory
    if factory is None:
        from db.session import make_session_factory
        factory = make_session_factory()
    _session_factory = factory


def use_memory():
    global _session_factory
    _session_factory = None


def use_auth(enabled=True):
    global _auth_enabled
    _auth_enabled = enabled


if os.environ.get('IOT_STORAGE') == 'sql':
    use_sql()
if os.environ.get('IOT_REQUIRE_SIGNATURE') == '1':
    use_auth(True)


async def require_auth(request: Request):
    '''Проверка подписи пакета хаба (только POST /telemetry/*).'''
    if not _auth_enabled:
        return
    if _session_factory is None:
        raise HTTPException(500, 'Проверка подписи требует режима SQL')
    auth.check(_session_factory, request.headers, await request.body())


@contextmanager
def unit_of_work():
    '''Одна транзакция на запрос: commit при успехе, rollback при сбое.'''
    if _session_factory is None:
        yield repo
        return
    session = _session_factory()
    try:
        yield SqlRepository(session)
        session.commit()
    except IntegrityError:  # сработал UNIQUE: дубликат пакета
        session.rollback()
        raise DuplicatePacket()
    except (UnknownZone, UnknownShelf, DuplicatePacket):
        session.commit()    # ожидаемые исходы: алерт UNKNOWN_SHELF сохраняется
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@router.post('/telemetry/climate', dependencies=[Depends(require_auth)])
def post_climate(p: ClimatePacket):
    try:
        with unit_of_work() as r:
            return climate.process(p, r)
    except (UnknownZone, UnknownSensor):
        raise HTTPException(404, 'Unknown zone')
    except DuplicatePacket:
        raise HTTPException(409, 'Duplicate packet')


@router.post('/telemetry/shelf', dependencies=[Depends(require_auth)])
def post_shelf(p: ShelfPacket):
    try:
        with unit_of_work() as r:
            return shelf.process(p, r)
    except (UnknownShelf, UnknownSensor):
        raise HTTPException(404, 'Unknown shelf')
    except DuplicatePacket:
        raise HTTPException(409, 'Duplicate packet')


@router.get('/telemetry')
def get_telemetry(limit: int = Query(50, ge=1, le=1000)):
    with unit_of_work() as r:
        return r.list_measurements(limit)


@router.get('/climate/status')
def get_climate_status():
    with unit_of_work() as r:
        return r.list_statuses()


@router.get('/inventory')
def get_inventory():
    with unit_of_work() as r:
        return [asdict(s) for s in r.list_shelves()]


@router.get('/alerts')
def get_alerts(severity: Optional[str] = None,
               limit: int = Query(100, ge=1, le=1000)):
    with unit_of_work() as r:
        return [asdict(a) for a in r.list_alerts(severity, limit)]


@router.get('/health')
def health():
    return {'status': 'ok'}