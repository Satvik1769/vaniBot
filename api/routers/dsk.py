"""DSK and leave management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from decimal import Decimal

from ..core.database import get_db
from ..models.dsk import (
    NearestDSKRequest,
    NearestDSKResponse,
    LeaveRequest,
    LeaveResponse,
    LeaveStatusRequest,
    LeaveStatusResponse,
    ActivationInfoResponse
)
from ..services import dsk_service

router = APIRouter(prefix="/dsk", tags=["DSK & Leaves"])


@router.post("/nearest", response_model=NearestDSKResponse)
async def find_nearest_dsk(
    request: NearestDSKRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Find nearest DSK (Dealer Service Kiosk) locations.

    Can search by coordinates, city, or service type.
    Service types: activation, repair, support, battery_replacement
    """
    dsk_list = await dsk_service.get_nearest_dsk(
        db=db,
        latitude=request.latitude,
        longitude=request.longitude,
        city=request.city,
        service_type=request.service_type,
        limit=request.limit
    )

    if dsk_list:
        msg = f"Found {len(dsk_list)} DSK location(s)"
        msg_hi = f"{len(dsk_list)} DSK location(s) mile"
    else:
        msg = "No DSK locations found matching your criteria"
        msg_hi = "Aapki search ke liye koi DSK nahi mila"

    return {
        "dsk_locations": dsk_list,
        "total_found": len(dsk_list),
        "service_filter": request.service_type,
        "message": msg,
        "message_hi": msg_hi
    }


@router.get("/nearest")
async def find_nearest_dsk_get(
    latitude: Optional[Decimal] = Query(default=None),
    longitude: Optional[Decimal] = Query(default=None),
    city: Optional[str] = Query(default=None),
    service_type: Optional[str] = Query(default=None),
    limit: int = Query(default=3, ge=1, le=10),
    db: AsyncSession = Depends(get_db)
):
    """Find nearest DSK using query parameters."""
    dsk_list = await dsk_service.get_nearest_dsk(
        db=db,
        latitude=latitude,
        longitude=longitude,
        city=city,
        service_type=service_type,
        limit=limit
    )

    return {
        "dsk_locations": dsk_list,
        "total_found": len(dsk_list)
    }


@router.get("/city/{city}")
async def get_dsk_by_city(
    city: str,
    service_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get all DSK locations in a city."""
    dsk_list = await dsk_service.get_nearest_dsk(
        db=db,
        city=city,
        service_type=service_type,
        limit=10
    )
    return {
        "city": city,
        "dsk_locations": dsk_list,
        "total_found": len(dsk_list)
    }


@router.get("/activation", response_model=ActivationInfoResponse)
async def get_activation_info(
    city: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db)
):
    """Get information about activation process and nearest DSK."""
    return await dsk_service.get_activation_info(db, city)


@router.post("/leave", response_model=LeaveResponse)
async def apply_for_leave(
    request: LeaveRequest,
    db: AsyncSession = Depends(get_db)
):
    """Submit a leave request."""
    # Validate dates
    if request.end_date < request.start_date:
        raise HTTPException(
            status_code=400,
            detail="End date must be after start date"
        )

    result = await dsk_service.apply_leave(
        db=db,
        phone_number=request.phone_number,
        start_date=request.start_date,
        end_date=request.end_date,
        reason=request.reason
    )

    if not result:
        raise HTTPException(status_code=404, detail="Driver not found")

    return result


@router.post("/leave/status", response_model=LeaveStatusResponse)
async def check_leave_status(
    request: LeaveStatusRequest,
    db: AsyncSession = Depends(get_db)
):
    """Check leave status for a driver."""
    return await dsk_service.get_leave_status(db, request.phone_number)


@router.get("/leave/{phone_number}", response_model=LeaveStatusResponse)
async def get_leave_status(
    phone_number: str,
    db: AsyncSession = Depends(get_db)
):
    """Get leave status using phone number."""
    return await dsk_service.get_leave_status(db, phone_number)