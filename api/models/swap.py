"""Swap and invoice models."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from uuid import UUID
from decimal import Decimal


class SwapBase(BaseModel):
    """Base swap model."""
    old_battery_id: Optional[str] = None
    new_battery_id: Optional[str] = None
    old_battery_charge_level: Optional[int] = None
    new_battery_charge_level: Optional[int] = None
    is_subscription_swap: bool = True
    charge_amount: Decimal = Decimal("0")


class SwapResponse(SwapBase):
    """Swap response model."""
    id: UUID
    driver_id: UUID
    station_id: UUID
    swap_time: datetime
    status: str
    station_name: Optional[str] = None
    station_code: Optional[str] = None
    invoice_number: Optional[str] = None

    class Config:
        from_attributes = True


class SwapHistoryRequest(BaseModel):
    """Request for swap history."""
    phone_number: str = Field(..., pattern=r"^[6-9]\d{9}$")
    time_period: str = Field(
        default="today",
        pattern=r"^(today|yesterday|last_week|last_month|all)$"
    )
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    limit: int = Field(default=20, ge=1, le=100)


class SwapHistoryResponse(BaseModel):
    """Response with swap history."""
    driver_id: UUID
    driver_name: Optional[str]
    phone_number: str
    time_period: str
    swaps: List[SwapResponse]
    total_swaps: int
    total_charged: Decimal
    total_free: int
    message: str
    message_hi: str


class InvoiceBase(BaseModel):
    """Base invoice model."""
    invoice_number: str
    invoice_type: str
    amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    description: Optional[str] = None
    description_hi: Optional[str] = None
    payment_status: str


class InvoiceResponse(InvoiceBase):
    """Invoice response model."""
    id: UUID
    driver_id: UUID
    swap_id: Optional[UUID] = None
    subscription_id: Optional[UUID] = None
    generated_at: datetime

    class Config:
        from_attributes = True


class InvoiceDetailRequest(BaseModel):
    """Request for invoice details."""
    phone_number: str = Field(..., pattern=r"^[6-9]\d{9}$")
    invoice_number: Optional[str] = None
    swap_id: Optional[UUID] = None
    date: Optional[date] = None


class InvoiceDetailResponse(BaseModel):
    """Response with invoice explanation."""
    invoice: InvoiceResponse
    explanation: str
    explanation_hi: str
    breakdown: List[dict]
    related_swap: Optional[SwapResponse] = None
    related_subscription: Optional[dict] = None