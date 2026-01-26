"""Station models."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from decimal import Decimal


class StationBase(BaseModel):
    """Base station model."""
    code: str
    name: str
    address: Optional[str] = None
    landmark: Optional[str] = None
    latitude: Decimal
    longitude: Decimal
    city: str
    pincode: Optional[str] = None
    operating_hours: str = "06:00-22:00"
    contact_phone: Optional[str] = None


class StationResponse(StationBase):
    """Station response model."""
    id: UUID
    is_active: bool

    class Config:
        from_attributes = True


class StationInventory(BaseModel):
    """Station inventory model."""
    available_batteries: int
    charging_batteries: int
    total_slots: int
    last_updated: datetime


class StationWithAvailability(StationResponse):
    """Station with inventory information."""
    inventory: Optional[StationInventory] = None
    distance_km: Optional[float] = None


class NearestStationsRequest(BaseModel):
    """Request for finding nearest stations."""
    latitude: Decimal = Field(..., ge=-90, le=90)
    longitude: Decimal = Field(..., ge=-180, le=180)
    limit: int = Field(default=5, ge=1, le=20)
    max_distance_km: float = Field(default=10.0, ge=0.1, le=50.0)


class NearestStationsResponse(BaseModel):
    """Response with nearest stations."""
    user_location: dict
    stations: List[StationWithAvailability]
    total_found: int


class StationAvailabilityRequest(BaseModel):
    """Request for checking station availability."""
    station_id: Optional[UUID] = None
    station_code: Optional[str] = None
    station_name: Optional[str] = None


class StationAvailabilityResponse(BaseModel):
    """Response with station availability details."""
    station: StationResponse
    available_batteries: int
    charging_batteries: int
    total_slots: int
    occupancy_percentage: float
    last_updated: datetime
    status: str = Field(description="'high' (>10), 'medium' (5-10), 'low' (<5)")
    status_message: str
    status_message_hi: str