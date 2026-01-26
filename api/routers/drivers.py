"""Driver management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.driver import (
    DriverCreate,
    DriverResponse,
    DriverIdentify,
    DriverProfile
)
from ..services import driver_service

router = APIRouter(prefix="/drivers", tags=["Drivers"])


@router.post("/identify")
async def identify_driver(
    request: DriverIdentify,
    db: AsyncSession = Depends(get_db)
):
    """
    Identify a driver by phone number.

    Returns driver info if exists, or creates a new driver.
    """
    driver, is_new = await driver_service.get_or_create_driver(db, request.phone_number)

    return {
        "driver": driver,
        "is_new": is_new,
        "message": "Welcome! Please complete your registration." if is_new else f"Welcome back{', ' + driver['name'] if driver.get('name') else ''}!",
        "message_hi": "Swagat hai! Apna registration complete karein." if is_new else f"Wapas swagat hai{', ' + driver['name'] if driver.get('name') else ''}!"
    }


@router.get("/profile/{phone_number}", response_model=DriverProfile)
async def get_driver_profile(
    phone_number: str,
    db: AsyncSession = Depends(get_db)
):
    """Get complete driver profile with subscription info."""
    profile = await driver_service.get_driver_profile(db, phone_number)
    if not profile:
        raise HTTPException(status_code=404, detail="Driver not found")
    return profile


@router.get("/{phone_number}")
async def get_driver(
    phone_number: str,
    db: AsyncSession = Depends(get_db)
):
    """Get driver by phone number."""
    driver = await driver_service.get_driver_by_phone(db, phone_number)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    return driver


@router.put("/{phone_number}/language")
async def update_language_preference(
    phone_number: str,
    language: str,
    db: AsyncSession = Depends(get_db)
):
    """Update driver's preferred language."""
    if language not in ["hi", "en", "hi-en"]:
        raise HTTPException(
            status_code=400,
            detail="Language must be 'hi', 'en', or 'hi-en'"
        )

    success = await driver_service.update_driver_language(db, phone_number, language)
    if not success:
        raise HTTPException(status_code=404, detail="Driver not found")

    return {
        "success": True,
        "message": f"Language preference updated to {language}",
        "message_hi": f"Language preference {language} mein update ho gayi"
    }