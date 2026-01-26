"""Subscription service for database operations."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List, Optional
from datetime import date
from decimal import Decimal


async def get_subscription_status(db: AsyncSession, phone_number: str) -> dict:
    """Get driver's current subscription status."""
    query = text("""
        SELECT * FROM v_active_subscriptions
        WHERE phone_number = :phone_number
        LIMIT 1
    """)
    result = await db.execute(query, {"phone_number": phone_number})
    row = result.fetchone()

    if row:
        data = dict(row._mapping)
        days_remaining = data.get("days_remaining", 0)
        swaps_remaining = data.get("swaps_remaining", -1)

        # Generate appropriate messages
        if days_remaining <= 0:
            msg = "Your subscription has expired. Please renew to continue."
            msg_hi = "Aapka subscription expire ho gaya hai. Continue karne ke liye renew karein."
        elif days_remaining <= 3:
            msg = f"Your {data['plan_name']} expires in {days_remaining} days. Renew soon!"
            msg_hi = f"Aapka {data['plan_name_hi'] or data['plan_name']} {days_remaining} din mein expire ho raha hai. Jaldi renew karein!"
        else:
            if swaps_remaining == -1:
                msg = f"Your {data['plan_name']} is active with unlimited swaps. {days_remaining} days remaining."
                msg_hi = f"Aapka {data['plan_name_hi'] or data['plan_name']} active hai unlimited swaps ke saath. {days_remaining} din bache hain."
            else:
                msg = f"Your {data['plan_name']} is active. {swaps_remaining} swaps remaining, {days_remaining} days left."
                msg_hi = f"Aapka {data['plan_name_hi'] or data['plan_name']} active hai. {swaps_remaining} swaps bache hain, {days_remaining} din bache hain."

        return {
            "has_active_subscription": True,
            "subscription": {
                "id": data["subscription_id"],
                "plan_code": data["plan_code"],
                "plan_name": data["plan_name"],
                "plan_name_hi": data.get("plan_name_hi"),
                "price": data["plan_price"],
                "start_date": data["start_date"],
                "end_date": data["end_date"],
                "days_remaining": days_remaining,
                "swaps_included": data["swaps_included"],
                "swaps_used": data["swaps_used"],
                "swaps_remaining": swaps_remaining,
                "status": data["status"],
                "auto_renew": data["auto_renew"],
                "is_expiring_soon": days_remaining <= 3
            },
            "message": msg,
            "message_hi": msg_hi
        }
    else:
        return {
            "has_active_subscription": False,
            "subscription": None,
            "message": "No active subscription found. Please subscribe to start swapping.",
            "message_hi": "Koi active subscription nahi mila. Swapping shuru karne ke liye subscribe karein."
        }


async def get_all_plans(db: AsyncSession) -> List[dict]:
    """Get all active subscription plans."""
    query = text("""
        SELECT id, code, name, name_hi, price, validity_days, swaps_included,
               extra_swap_price, description_en, description_hi, is_active
        FROM subscription_plans
        WHERE is_active = true
        ORDER BY price ASC
    """)
    result = await db.execute(query)
    rows = result.fetchall()
    return [dict(row._mapping) for row in rows]


async def get_plan_by_code(db: AsyncSession, plan_code: str) -> Optional[dict]:
    """Get subscription plan by code."""
    query = text("""
        SELECT id, code, name, name_hi, price, validity_days, swaps_included,
               extra_swap_price, description_en, description_hi
        FROM subscription_plans
        WHERE code = :code AND is_active = true
    """)
    result = await db.execute(query, {"code": plan_code})
    row = result.fetchone()
    return dict(row._mapping) if row else None


async def create_subscription(
    db: AsyncSession,
    driver_id: str,
    plan_code: str,
    auto_renew: bool = False
) -> Optional[dict]:
    """Create a new subscription for driver."""
    # Get plan details
    plan = await get_plan_by_code(db, plan_code)
    if not plan:
        return None

    # Calculate dates
    start_date = date.today()
    from datetime import timedelta
    end_date = start_date + timedelta(days=plan["validity_days"])

    # Expire any existing active subscriptions
    expire_query = text("""
        UPDATE driver_subscriptions
        SET status = 'expired'
        WHERE driver_id = :driver_id AND status = 'active'
    """)
    await db.execute(expire_query, {"driver_id": driver_id})

    # Create new subscription
    query = text("""
        INSERT INTO driver_subscriptions
        (driver_id, plan_id, start_date, end_date, status, swaps_used, auto_renew)
        VALUES (:driver_id, :plan_id, :start_date, :end_date, 'active', 0, :auto_renew)
        RETURNING id, start_date, end_date
    """)
    result = await db.execute(query, {
        "driver_id": driver_id,
        "plan_id": plan["id"],
        "start_date": start_date,
        "end_date": end_date,
        "auto_renew": auto_renew
    })
    await db.commit()
    row = result.fetchone()

    if row:
        sub = dict(row._mapping)
        tax = round(plan["price"] * Decimal("0.18"), 2)
        total = plan["price"] + tax

        return {
            "success": True,
            "subscription_id": sub["id"],
            "plan_name": plan["name"],
            "price": plan["price"],
            "tax": tax,
            "total": total,
            "validity_days": plan["validity_days"],
            "start_date": sub["start_date"],
            "end_date": sub["end_date"],
            "payment_link": f"https://pay.batterysmart.in/subscription/{sub['id']}",
            "message": f"Your {plan['name']} subscription is active from {sub['start_date']} to {sub['end_date']}",
            "message_hi": f"Aapka {plan.get('name_hi') or plan['name']} subscription {sub['start_date']} se {sub['end_date']} tak active hai"
        }
    return None


async def get_pricing_info(db: AsyncSession) -> dict:
    """Get pricing information for all plans."""
    plans = await get_all_plans(db)
    return {
        "plans": plans,
        "currency": "INR",
        "tax_rate": Decimal("0.18"),
        "message": "Choose the plan that suits your needs. Monthly plan offers best value!",
        "message_hi": "Apni zaroorat ke hisaab se plan chunein. Monthly plan mein sabse achhi value hai!"
    }