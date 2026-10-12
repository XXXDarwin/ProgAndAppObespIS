from dataclasses import dataclass
from datetime import datetime


@dataclass
class ZoneLimits:
    zone: str
    t_min: float
    t_max: float
    h_min: float
    h_max: float


@dataclass
class Shelf:
    shelf_id: str
    zone: str
    product_name: str
    unit_weight_g: float
    quantity: int
    last_weight_g: float | None = None


@dataclass
class Alert:
    id: int
    type: str
    severity: str
    source: str
    details: str
    created: datetime