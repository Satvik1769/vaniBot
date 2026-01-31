"""Station and availability endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from decimal import Decimal
from uuid import UUID

from ..core.database import get_db
from ..models.station import (
    StationResponse,
    StationWithAvailability,
    NearestStationsRequest,
    NearestStationsResponse,
    StationAvailabilityRequest,
    StationAvailabilityResponse
)
from ..services import station_service
from ..services.geolocation_service import get_user_location, get_nearest_stations as geo_nearest

router = APIRouter(prefix="/stations", tags=["Stations"])


@router.post("/nearest", response_model=NearestStationsResponse)
async def find_nearest_stations(
    request: NearestStationsRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Find nearest stations based on coordinates.

    Returns stations within max_distance_km, sorted by distance.
    """
    stations = await station_service.get_nearest_stations(
        db=db,
        latitude=request.latitude,
        longitude=request.longitude,
        limit=request.limit,
        max_distance_km=request.max_distance_km
    )
    return {
        "user_location": {
            "latitude": float(request.latitude),
            "longitude": float(request.longitude)
        },
        "stations": stations,
        "total_found": len(stations)
    }


@router.get("/nearest")
async def find_nearest_stations_get(
    latitude: Decimal = Query(..., description="User's latitude"),
    longitude: Decimal = Query(..., description="User's longitude"),
    limit: int = Query(default=5, ge=1, le=20),
    max_distance_km: float = Query(default=10.0),
    db: AsyncSession = Depends(get_db)
):
    """Find nearest stations using GET parameters."""
    stations = await station_service.get_nearest_stations(
        db=db,
        latitude=latitude,
        longitude=longitude,
        limit=limit,
        max_distance_km=max_distance_km
    )
    return {
        "user_location": {
            "latitude": float(latitude),
            "longitude": float(longitude)
        },
        "stations": stations,
        "total_found": len(stations)
    }


@router.get("/city/{city}")
async def get_stations_by_city(
    city: str,
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """Get all stations in a city."""
    stations = await station_service.get_stations_by_city(db, city, limit)
    return {
        "city": city,
        "stations": stations,
        "total_found": len(stations)
    }


@router.get("/search")
async def search_stations(
    q: str = Query(..., min_length=2, description="Search term"),
    limit: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db)
):
    """Search stations by name, code, or location."""
    stations = await station_service.search_stations(db, q, limit)
    return {
        "query": q,
        "stations": stations,
        "total_found": len(stations)
    }


@router.post("/availability", response_model=StationAvailabilityResponse)
async def check_station_availability(
    request: StationAvailabilityRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Check availability at a specific station.

    Provide one of: station_id, station_code, or station_name.
    """
    result = await station_service.get_station_availability(
        db=db,
        station_id=str(request.station_id) if request.station_id else None,
        station_code=request.station_code,
        station_name=request.station_name
    )
    if not result:
        raise HTTPException(status_code=404, detail="Station not found")

    return {
        "station": {
            "id": result["id"],
            "code": result["code"],
            "name": result["name"],
            "address": result["address"],
            "landmark": result["landmark"],
            "latitude": result["latitude"],
            "longitude": result["longitude"],
            "city": result["city"],
            "pincode": result["pincode"],
            "operating_hours": result["operating_hours"],
            "contact_phone": result["contact_phone"],
            "is_active": result["is_active"]
        },
        "available_batteries": result["available_batteries"],
        "charging_batteries": result["charging_batteries"],
        "total_slots": result["total_slots"],
        "occupancy_percentage": result["occupancy_percentage"],
        "last_updated": result["last_updated"],
        "status": result["status"],
        "status_message": result["status_message"],
        "status_message_hi": result["status_message_hi"]
    }


@router.get("/availability/{identifier}")
async def check_availability_simple(
    identifier: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Check availability by station code or name.

    The identifier can be a station code (e.g., DLH-LXN-001) or partial name.
    """
    # Try as code first
    result = await station_service.get_station_availability(
        db=db,
        station_code=identifier
    )
    if not result:
        # Try as name
        result = await station_service.get_station_availability(
            db=db,
            station_name=identifier
        )

    if not result:
        raise HTTPException(status_code=404, detail="Station not found")

    return {
        "station": {
            "id": result["id"],
            "code": result["code"],
            "name": result["name"],
            "address": result["address"],
            "city": result["city"]
        },
        "available_batteries": result["available_batteries"],
        "status": result["status"],
        "status_message": result["status_message"],
        "status_message_hi": result["status_message_hi"]
    }


@router.get("/nearest-by-phone/{phone_number}")
async def find_nearest_by_phone(
    phone_number: str,
    request: Request,
    limit: int = Query(default=5, ge=1, le=10),
    min_batteries: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Find nearest stations for a user by their phone number.

    Uses IP geolocation or registered city to determine location.
    Optionally filter by minimum available batteries.
    """
    # Get client IP for geolocation
    client_ip = request.client.host if request.client else None

    # Get user location
    location = await get_user_location(
        db=db,
        phone_number=phone_number,
        ip_address=client_ip
    )

    # Find nearest stations
    stations = await geo_nearest(
        db=db,
        latitude=location["latitude"],
        longitude=location["longitude"],
        limit=limit,
        min_available_batteries=min_batteries
    )

    return {
        "phone_number": phone_number,
        "user_location": location,
        "stations": stations,
        "total_found": len(stations),
        "message": f"Found {len(stations)} stations near you." if stations else "No stations found nearby.",
        "message_hi": f"Aapke paas {len(stations)} stations mile." if stations else "Aapke paas koi station nahi mila."
    }


@router.get("/dsk/nearest-by-phone/{phone_number}")
async def find_nearest_dsk_by_phone(
    phone_number: str,
    request: Request,
    limit: int = Query(default=3, ge=1, le=5),
    db: AsyncSession = Depends(get_db)
):
    """
    Find nearest DSK (Dealer Service Kiosk) for a user by their phone number.

    Uses IP geolocation or registered city to determine location.
    """
    from ..services.geolocation_service import get_nearest_dsk as geo_dsk

    # Get client IP for geolocation
    client_ip = request.client.host if request.client else None

    # Get user location
    location = await get_user_location(
        db=db,
        phone_number=phone_number,
        ip_address=client_ip
    )

    # Find nearest DSK
    dsk_list = await geo_dsk(
        db=db,
        latitude=location["latitude"],
        longitude=location["longitude"],
        limit=limit
    )

    return {
        "phone_number": phone_number,
        "user_location": location,
        "dsk_locations": dsk_list,
        "total_found": len(dsk_list),
        "message": f"Found {len(dsk_list)} DSK locations near you." if dsk_list else "No DSK found nearby.",
        "message_hi": f"Aapke paas {len(dsk_list)} DSK mile." if dsk_list else "Aapke paas koi DSK nahi mila."
    }