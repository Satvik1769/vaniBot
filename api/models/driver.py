"""Driver models."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class DriverBase(BaseModel):
    """Base driver model."""
    phone_number: str = Field(..., pattern=r"^[6-9]\d{9}$", description="Indian mobile number")
    name: Optional[str] = None
    email: Optional[str] = None
    preferred_language: str = Field(default="hi-en", pattern=r"^(hi|en|hi-en)$")
    city: Optional[str] = None


class DriverCreate(DriverBase):
    """Model for creating a driver."""
    pass


class DriverResponse(DriverBase):
    """Driver response model."""
    id: UUID
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


class DriverIdentify(BaseModel):
    """Model for identifying driver by phone."""
    phone_number: str = Field(..., pattern=r"^[6-9]\d{9}$")


class DriverProfile(BaseModel):
    """Complete driver profile with subscription info."""
    id: UUID
    phone_number: str
    name: Optional[str]
    preferred_language: str
    city: Optional[str]
    created_at: datetime
    is_active: bool
    current_subscription: Optional["SubscriptionSummary"] = None
    total_swaps_this_month: int = 0
    pending_leaves: int = 0


# Forward reference
from .subscription import SubscriptionSummary
DriverProfile.model_rebuild()