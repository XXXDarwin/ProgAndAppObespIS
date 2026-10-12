from datetime import datetime

from pydantic import BaseModel, Field


class ClimatePacket(BaseModel):
    zone: str = Field(pattern='^[A-Z]$')
    temperature: float = Field(ge=-40, le=85)
    humidity: float = Field(ge=0, le=100)
    timestamp: datetime


class ShelfPacket(BaseModel):
    shelf_id: str = Field(pattern='^[A-Z][0-9]+-[0-9]+-[0-9]+$')
    weight_g: float = Field(ge=0)
    timestamp: datetime