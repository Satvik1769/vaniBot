"""Driver service for database operations."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from uuid import UUID
from datetime import datetime


async def get_driver_by_phone(db: AsyncSession, phone_number: str) -> Optional[dict]:
    """Get driver by phone number."""
    query = text("""
        SELECT id, phone_number, driver_name, email, preferred_language, city, created_at, is_active
        FROM drivers
        WHERE phone_number = :phone_number AND is_active = true
    """)
    result = await db.execute(query, {"phone_number": phone_number})
    row = result.fetchone()
    if row:
        return dict(row._mapping)
    return None


async def get_driver_profile(db: AsyncSession, phone_number: str) -> Optional[dict]:
    """Get complete driver profile with subscription info."""
    driver = await get_driver_by_phone(db, phone_number)
    if not driver:
        return None

    # Get active subscription
    sub_query = text("""
        SELECT * FROM v_active_subscriptions
        WHERE phone_number = :phone_number
        LIMIT 1
    """)
    sub_result = await db.execute(sub_query, {"phone_number": phone_number})
    subscription = sub_result.fetchone()

    # Get monthly swap count
    swap_query = text("""
        SELECT COUNT(*) as count
        FROM swaps
        WHERE driver_id = :driver_id
        AND swap_time >= date_trunc('month', CURRENT_DATE)
    """)
    swap_result = await db.execute(swap_query, {"driver_id": driver["id"]})
    monthly_swaps = swap_result.scalar() or 0

    # Get pending leaves count
    leave_query = text("""
        SELECT COUNT(*) as count
        FROM driver_leaves
        WHERE driver_id = :driver_id AND status = 'pending'
    """)
    leave_result = await db.execute(leave_query, {"driver_id": driver["id"]})
    pending_leaves = leave_result.scalar() or 0

    profile = {
        **driver,
        "current_subscription": dict(subscription._mapping) if subscription else None,
        "total_swaps_this_month": monthly_swaps,
        "pending_leaves": pending_leaves,
    }
    return profile


async def create_driver(db: AsyncSession, phone_number: str, name: str = None,
                        preferred_language: str = "hi-en", city: str = None) -> dict:
    """Create a new driver."""
    query = text("""
        INSERT INTO drivers (phone_number, name, preferred_language, city)
        VALUES (:phone_number, :name, :preferred_language, :city)
        RETURNING id, phone_number, name, preferred_language, city, created_at, is_active
    """)
    result = await db.execute(query, {
        "phone_number": phone_number,
        "name": name,
        "preferred_language": preferred_language,
        "city": city
    })
    await db.commit()
    row = result.fetchone()
    return dict(row._mapping)


async def update_driver_language(db: AsyncSession, phone_number: str,
                                  preferred_language: str) -> bool:
    """Update driver's preferred language."""
    query = text("""
        UPDATE drivers
        SET preferred_language = :preferred_language
        WHERE phone_number = :phone_number
    """)
    result = await db.execute(query, {
        "phone_number": phone_number,
        "preferred_language": preferred_language
    })
    await db.commit()
    return result.rowcount > 0


async def get_or_create_driver(db: AsyncSession, phone_number: str) -> tuple[dict, bool]:
    """Get existing driver or create new one. Returns (driver, is_new)."""
    driver = await get_driver_by_phone(db, phone_number)
    if driver:
        return driver, False

    new_driver = await create_driver(db, phone_number)
    return new_driver, True