"""Swap history and invoice endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import date
from uuid import UUID

from ..core.database import get_db
from ..models.swap import (
    SwapHistoryRequest,
    SwapHistoryResponse,
    InvoiceDetailRequest,
    InvoiceDetailResponse
)
from ..services import swap_service

router = APIRouter(prefix="/swaps", tags=["Swaps"])


@router.post("/history", response_model=SwapHistoryResponse)
async def get_swap_history(
    request: SwapHistoryRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Get swap history for a driver.

    Time periods: today, yesterday, last_week, last_month, all
    Or provide custom start_date and end_date.
    """
    result = await swap_service.get_swap_history(
        db=db,
        phone_number=request.phone_number,
        time_period=request.time_period,
        start_date=request.start_date,
        end_date=request.end_date,
        limit=request.limit
    )
    return result


@router.get("/history/{phone_number}", response_model=SwapHistoryResponse)
async def get_swap_history_simple(
    phone_number: str,
    time_period: str = "today",
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """Get swap history with simple query parameters."""
    result = await swap_service.get_swap_history(
        db=db,
        phone_number=phone_number,
        time_period=time_period,
        limit=limit
    )
    return result


@router.post("/invoice", response_model=InvoiceDetailResponse)
async def get_invoice_details(
    request: InvoiceDetailRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Get invoice details with explanation.

    Provide one of: invoice_number, swap_id, or date.
    If none provided, returns most recent invoice.
    """
    result = await swap_service.get_invoice_details(
        db=db,
        phone_number=request.phone_number,
        invoice_number=request.invoice_number,
        swap_id=str(request.swap_id) if request.swap_id else None,
        invoice_date=request.date
    )
    if not result:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return result


@router.get("/invoice/{phone_number}", response_model=InvoiceDetailResponse)
async def get_latest_invoice(
    phone_number: str,
    invoice_number: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get latest or specific invoice for a driver."""
    result = await swap_service.get_invoice_details(
        db=db,
        phone_number=phone_number,
        invoice_number=invoice_number
    )
    if not result:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return result