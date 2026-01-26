"""Subscription models."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from uuid import UUID
from decimal import Decimal


class SubscriptionPlanBase(BaseModel):
    """Base subscription plan model."""
    code: str
    name: str
    name_hi: Optional[str] = None
    price: Decimal
    validity_days: int
    swaps_included: int = Field(description="-1 for unlimited")
    extra_swap_price: Decimal = Decimal("35.00")
    description_en: Optional[str] = None
    description_hi: Optional[str] = None


class SubscriptionPlanResponse(SubscriptionPlanBase):
    """Subscription plan response model."""
    id: UUID
    is_active: bool

    class Config:
        from_attributes = True


class SubscriptionSummary(BaseModel):
    """Summary of driver's current subscription."""
    id: UUID
    plan_code: str
    plan_name: str
    plan_name_hi: Optional[str]
    price: Decimal
    start_date: date
    end_date: date
    days_remaining: int
    swaps_included: int
    swaps_used: int
    swaps_remaining: int = Field(description="-1 for unlimited")
    status: str
    auto_renew: bool
    is_expiring_soon: bool = Field(description="True if <= 3 days remaining")


class SubscriptionStatusRequest(BaseModel):
    """Request for checking subscription status."""
    phone_number: str = Field(..., pattern=r"^[6-9]\d{9}$")


class SubscriptionStatusResponse(BaseModel):
    """Response with subscription status."""
    driver_id: UUID
    driver_name: Optional[str]
    phone_number: str
    has_active_subscription: bool
    subscription: Optional[SubscriptionSummary] = None
    message: str
    message_hi: str


class SubscriptionRenewalRequest(BaseModel):
    """Request for subscription renewal."""
    phone_number: str = Field(..., pattern=r"^[6-9]\d{9}$")
    plan_code: str = Field(..., pattern=r"^(DAILY|WEEKLY|MONTHLY|YEARLY)$")
    auto_renew: bool = False


class SubscriptionRenewalResponse(BaseModel):
    """Response for subscription renewal."""
    success: bool
    subscription_id: Optional[UUID] = None
    plan_name: str
    price: Decimal
    tax: Decimal
    total: Decimal
    validity_days: int
    start_date: date
    end_date: date
    payment_link: Optional[str] = None
    message: str
    message_hi: str


class PricingResponse(BaseModel):
    """Response with all pricing information."""
    plans: List[SubscriptionPlanResponse]
    currency: str = "INR"
    tax_rate: Decimal = Decimal("0.18")
    message: str
    message_hi: str