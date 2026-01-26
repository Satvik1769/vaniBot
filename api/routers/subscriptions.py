"""Subscription and pricing endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.subscription import (
    SubscriptionStatusRequest,
    SubscriptionStatusResponse,
    SubscriptionRenewalRequest,
    SubscriptionRenewalResponse,
    PricingResponse
)
from ..services import subscription_service, driver_service

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.post("/status", response_model=SubscriptionStatusResponse)
async def check_subscription_status(
    request: SubscriptionStatusRequest,
    db: AsyncSession = Depends(get_db)
):
    """Check subscription status for a driver."""
    # Get driver
    driver = await driver_service.get_driver_by_phone(db, request.phone_number)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    result = await subscription_service.get_subscription_status(db, request.phone_number)

    return {
        "driver_id": driver["id"],
        "driver_name": driver.get("name"),
        "phone_number": request.phone_number,
        **result
    }


@router.get("/status/{phone_number}", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    phone_number: str,
    db: AsyncSession = Depends(get_db)
):
    """Get subscription status using phone number."""
    driver = await driver_service.get_driver_by_phone(db, phone_number)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    result = await subscription_service.get_subscription_status(db, phone_number)

    return {
        "driver_id": driver["id"],
        "driver_name": driver.get("name"),
        "phone_number": phone_number,
        **result
    }


@router.post("/renew", response_model=SubscriptionRenewalResponse)
async def renew_subscription(
    request: SubscriptionRenewalRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Renew or create a new subscription.

    Plan codes: DAILY, WEEKLY, MONTHLY, YEARLY
    """
    # Get driver
    driver = await driver_service.get_driver_by_phone(db, request.phone_number)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    result = await subscription_service.create_subscription(
        db=db,
        driver_id=str(driver["id"]),
        plan_code=request.plan_code,
        auto_renew=request.auto_renew
    )

    if not result:
        raise HTTPException(status_code=400, detail="Invalid plan code or subscription creation failed")

    return result


@router.get("/plans", response_model=PricingResponse)
async def get_all_plans(db: AsyncSession = Depends(get_db)):
    """Get all available subscription plans with pricing."""
    return await subscription_service.get_pricing_info(db)


@router.get("/pricing", response_model=PricingResponse)
async def get_pricing(db: AsyncSession = Depends(get_db)):
    """Alias for /plans - Get pricing information."""
    return await subscription_service.get_pricing_info(db)


@router.get("/plans/{plan_code}")
async def get_plan_details(
    plan_code: str,
    db: AsyncSession = Depends(get_db)
):
    """Get details of a specific plan."""
    plan = await subscription_service.get_plan_by_code(db, plan_code.upper())
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan