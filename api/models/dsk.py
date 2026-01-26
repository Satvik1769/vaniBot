"""DSK (Dealer Service Kiosk) and leave models."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from uuid import UUID
from decimal import Decimal


class DSKBase(BaseModel):
    """Base DSK model."""
    code: str
    name: str
    address: Optional[str] = None
    landmark: Optional[str] = None
    latitude: Decimal
    longitude: Decimal
    city: str
    pincode: Optional[str] = None
    phone: Optional[str] = None
    operating_hours: str = "09:00-18:00"
    services: List[str] = []


class DSKResponse(DSKBase):
    """DSK response model."""
    id: UUID
    is_active: bool
    distance_km: Optional[float] = None

    class Config:
        from_attributes = True


class NearestDSKRequest(BaseModel):
    """Request for finding nearest DSK."""
    latitude: Optional[Decimal] = Field(default=None, ge=-90, le=90)
    longitude: Optional[Decimal] = Field(default=None, ge=-180, le=180)
    city: Optional[str] = None
    service_type: Optional[str] = Field(
        default=None,
        pattern=r"^(activation|repair|support|battery_replacement)$"
    )
    limit: int = Field(default=3, ge=1, le=10)


class NearestDSKResponse(BaseModel):
    """Response with nearest DSK locations."""
    dsk_locations: List[DSKResponse]
    total_found: int
    service_filter: Optional[str]
    message: str
    message_hi: str


class LeaveRequest(BaseModel):
    """Request for applying leave."""
    phone_number: str = Field(..., pattern=r"^[6-9]\d{9}$")
    start_date: date
    end_date: date
    reason: Optional[str] = None


class LeaveResponse(BaseModel):
    """Response for leave application."""
    id: UUID
    driver_id: UUID
    start_date: date
    end_date: date
    days: int
    reason: Optional[str]
    status: str
    message: str
    message_hi: str


class LeaveStatusRequest(BaseModel):
    """Request for checking leave status."""
    phone_number: str = Field(..., pattern=r"^[6-9]\d{9}$")


class LeaveStatusResponse(BaseModel):
    """Response with leave status."""
    driver_id: UUID
    driver_name: Optional[str]
    phone_number: str
    pending_leaves: List[LeaveResponse]
    approved_leaves: List[LeaveResponse]
    total_pending: int
    total_approved: int
    message: str
    message_hi: str


class ActivationInfoResponse(BaseModel):
    """Response with activation information."""
    nearest_dsk: DSKResponse
    required_documents: List[str]
    required_documents_hi: List[str]
    process_steps: List[str]
    process_steps_hi: List[str]
    estimated_time: str
    estimated_time_hi: str
    contact_number: str
    message: str
    message_hi: str