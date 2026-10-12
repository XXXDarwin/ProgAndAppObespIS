# iot_server/api/routes.py
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from repositories.memory import MemoryRepository
from schemas.telemetry import ClimatePacket, ShelfPacket
from services import climate, shelf
from services.errors import DuplicatePacket, UnknownShelf, UnknownZone

router = APIRouter()
repo = MemoryRepository(seed=True)  # в ЛР №4 заменяется на SqlRepository


@router.post('/telemetry/climate')
def post_climate(p: ClimatePacket):
    try:
        return climate.process(p, repo)
    except UnknownZone:
        raise HTTPException(404, 'Unknown zone')


@router.post('/telemetry/shelf')
def post_shelf(p: ShelfPacket):
    try:
        return shelf.process(p, repo)
    except UnknownShelf:
        raise HTTPException(404, 'Unknown shelf')
    except DuplicatePacket:
        raise HTTPException(409, 'Duplicate packet')


@router.get('/telemetry')
def get_telemetry(limit: int = Query(50, ge=1, le=1000)):
    return repo.list_measurements(limit)


@router.get('/climate/status')
def get_climate_status():
    return repo.list_statuses()


@router.get('/inventory')
def get_inventory():
    return [asdict(s) for s in repo.list_shelves()]


@router.get('/alerts')
def get_alerts(severity: Optional[str] = None,
               limit: int = Query(100, ge=1, le=1000)):
    return [asdict(a) for a in repo.list_alerts(severity, limit)]


@router.get('/health')
def health():
    return {'status': 'ok'}