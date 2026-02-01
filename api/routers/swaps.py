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
    time_period: str = "all",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """
    Get swap history with simple query parameters.

    Time periods: today, yesterday, last_week, last_month, this_week, this_month,
                  last_year, this_year, all, or a number (e.g., "7" for last 7 days)
    Or provide custom start_date and end_date (YYYY-MM-DD format).
    """
    result = await swap_service.get_swap_history(
        db=db,
        phone_number=phone_number,
        time_period=time_period,
        start_date=start_date,
        end_date=end_date,
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


@router.get("/invoice-with-penalty/{phone_number}")
async def get_invoice_with_penalty(
    phone_number: str,
    invoice_number: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get invoice details with penalty information.

    If battery not returned after 4 days of subscription end,
    penalty of Rs.80/day is applicable.
    """
    result = await swap_service.get_invoice_with_penalty(
        db=db,
        phone_number=phone_number,
        invoice_number=invoice_number
    )
    return result


@router.get("/penalty/{phone_number}")
async def get_penalty_details(
    phone_number: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get penalty details for unreturned battery.

    Penalty: Rs.80/day after 4 days grace period past subscription end.
    """
    result = await swap_service.get_penalty_details(
        db=db,
        phone_number=phone_number
    )
    if not result:
        return {
            "has_penalty": False,
            "message": "No active subscription found",
            "message_hi": "Koi active subscription nahi mila"
        }
    return result


@router.post("/history/send-sms/{phone_number}")
async def send_swap_history_sms(
    phone_number: str,
    time_period: str = "all",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get swap history and send it via SMS to the user.

    Time periods: today, yesterday, last_week, last_month, this_week, this_month,
                  last_year, this_year, all, or a number (e.g., "7" for last 7 days)
    """
    from ..services.sms_service import send_swap_history_sms as sms_send

    # Get swap history
    history = await swap_service.get_swap_history(
        db=db,
        phone_number=phone_number,
        time_period=time_period,
        start_date=start_date,
        end_date=end_date,
        limit=10
    )

    # Send SMS
    sms_result = await sms_send(
        db=db,
        phone_number=phone_number,
        swaps=history.get("swaps", []),
        time_period=time_period,
        user_id=str(history.get("driver_id")) if history.get("driver_id") else None
    )

    return {
        "swap_history": history,
        "sms_sent": sms_result.get("success", False),
        "sms_status": sms_result.get("status"),
        "message": f"Swap history SMS sent to {phone_number}" if sms_result.get("success") else "SMS sending failed",
        "message_hi": f"Swap history SMS {phone_number} pe bhej di" if sms_result.get("success") else "SMS bhejne mein problem hui"
    }