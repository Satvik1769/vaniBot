"""Subscription service for database operations."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List, Optional
from datetime import date
from decimal import Decimal


async def get_subscription_status(db: AsyncSession, phone_number: str) -> dict:
    """Get driver's current subscription status by phone number."""
    query = text("""
        SELECT
            ds.id as subscription_id,
            ds.driver_id,
            ds.plan_id,
            ds.start_date,
            ds.end_date,
            ds.status,
            ds.swaps_used,
            ds.auto_renew,
            ds.battery_id,
            ds.battery_returned,
            sp.code as plan_code,
            sp.name as plan_name,
            sp.name_hi as plan_name_hi,
            sp.price as plan_price,
            sp.validity_days,
            sp.swaps_included,
            sp.extra_swap_price,
            d.driver_name,
            d.phone_number,
            (ds.end_date - CURRENT_DATE) as days_remaining,
            CASE
                WHEN sp.swaps_included = -1 THEN -1
                ELSE GREATEST(0, sp.swaps_included - COALESCE(ds.swaps_used, 0))
            END as swaps_remaining
        FROM driver_subscriptions ds
        JOIN drivers d ON ds.driver_id = d.id
        JOIN subscription_plans sp ON ds.plan_id = sp.id
        WHERE d.phone_number = :phone_number
        AND ds.status = 'active'
        ORDER BY ds.end_date DESC
        LIMIT 1
    """)
    result = await db.execute(query, {"phone_number": phone_number})
    row = result.fetchone()

    if row:
        data = dict(row._mapping)
        days_remaining = int(data.get("days_remaining", 0))
        swaps_remaining = int(data.get("swaps_remaining", -1))
        swaps_included = data.get("swaps_included", 0)
        swaps_used = data.get("swaps_used", 0)

        # Generate appropriate messages
        if days_remaining <= 0:
            msg = "Your subscription has expired. Please renew to continue."
            msg_hi = "Aapka subscription expire ho gaya hai. Continue karne ke liye renew karein."
            is_expired = True
        elif days_remaining <= 3:
            msg = f"Your {data['plan_name']} expires in {days_remaining} days. Renew soon!"
            msg_hi = f"Aapka {data.get('plan_name_hi') or data['plan_name']} {days_remaining} din mein expire ho raha hai. Jaldi renew karein!"
            is_expired = False
        else:
            is_expired = False
            if swaps_remaining == -1:
                msg = f"Your {data['plan_name']} is active with unlimited swaps. {days_remaining} days remaining."
                msg_hi = f"Aapka {data.get('plan_name_hi') or data['plan_name']} active hai unlimited swaps ke saath. {days_remaining} din bache hain."
            else:
                msg = f"Your {data['plan_name']} is active. {swaps_remaining} swaps remaining, {days_remaining} days left."
                msg_hi = f"Aapka {data.get('plan_name_hi') or data['plan_name']} active hai. {swaps_remaining} swaps bache hain, {days_remaining} din bache hain."

        return {
            "has_active_subscription": not is_expired,
            "is_expired": is_expired,
            "driver_id": str(data["driver_id"]),
            "driver_name": data.get("driver_name"),
            "subscription": {
                "id": str(data["subscription_id"]),
                "plan_id": str(data["plan_id"]),
                "plan_code": data["plan_code"],
                "plan_name": data["plan_name"],
                "plan_name_hi": data.get("plan_name_hi"),
                "price": float(data["plan_price"]),
                "start_date": data["start_date"],
                "end_date": data["end_date"],
                "days_remaining": days_remaining,
                "validity_days": data.get("validity_days"),
                "swaps_included": swaps_included,
                "swaps_used": swaps_used,
                "swaps_remaining": swaps_remaining,
                "extra_swap_price": float(data.get("extra_swap_price", 0)) if data.get("extra_swap_price") else None,
                "status": data["status"],
                "auto_renew": data.get("auto_renew", False),
                "battery_id": data.get("battery_id"),
                "battery_returned": data.get("battery_returned"),
                "is_expiring_soon": days_remaining <= 3 and days_remaining > 0
            },
            "message": msg,
            "message_hi": msg_hi
        }
    else:
        return {
            "has_active_subscription": False,
            "is_expired": True,
            "driver_id": None,
            "driver_name": None,
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

    # Format plans with GST breakdown
    formatted_plans = []
    for plan in plans:
        price = Decimal(str(plan["price"]))
        gst = price * Decimal("0.18")
        total = price + gst

        formatted_plans.append({
            **plan,
            "gst_amount": float(gst),
            "total_with_gst": float(total),
            "per_swap_cost": float(price / plan["swaps_included"]) if plan["swaps_included"] > 0 else 0
        })

    return {
        "plans": formatted_plans,
        "currency": "INR",
        "tax_rate": Decimal("0.18"),
        "gst_percentage": 18,
        "message": "Choose the plan that suits your needs. Monthly plan offers best value!",
        "message_hi": "Apni zaroorat ke hisaab se plan chunein. Monthly plan mein sabse achhi value hai!"
    }


async def initiate_renewal(
    db: AsyncSession,
    phone_number: str,
    plan_code: str
) -> dict:
    """Initiate subscription renewal with payment link."""
    from .payment_service import create_payment_order
    from .sms_service import send_payment_link_sms

    # Get driver
    driver_query = text("SELECT id, driver_name FROM drivers WHERE phone_number = :phone")
    driver_result = await db.execute(driver_query, {"phone": phone_number})
    driver_row = driver_result.fetchone()

    if not driver_row:
        return {
            "success": False,
            "error": "Driver not found",
            "message": "Driver not found. Please register first.",
            "message_hi": "Driver nahi mila. Pehle registration karein."
        }

    driver_id = str(driver_row[0])
    driver_name = driver_row[1]

    # Get plan details
    plan = await get_plan_by_code(db, plan_code.upper())
    if not plan:
        return {
            "success": False,
            "error": "Plan not found",
            "message": f"Plan '{plan_code}' not found. Available: DAILY, WEEKLY, MONTHLY, YEARLY",
            "message_hi": f"Plan '{plan_code}' nahi mila. Available: DAILY, WEEKLY, MONTHLY, YEARLY"
        }

    # Create payment order
    payment_result = await create_payment_order(
        db=db,
        user_id=driver_id,
        plan_id=str(plan["id"]),
        amount=float(plan["price"]),
        phone_number=phone_number
    )

    if not payment_result.get("success"):
        return {
            "success": False,
            "error": "Payment order failed",
            "message": "Could not create payment order. Please try again.",
            "message_hi": "Payment order nahi ban paya. Kripya dobara try karein."
        }

    # Send payment link via SMS
    sms_result = await send_payment_link_sms(
        db=db,
        phone_number=phone_number,
        payment_link=payment_result["payment_link"],
        plan_name=plan.get("name_hi") or plan["name"],
        amount=payment_result["total_amount"],
        user_id=driver_id
    )

    return {
        "success": True,
        "driver_name": driver_name,
        "plan_name": plan["name"],
        "plan_name_hi": plan.get("name_hi"),
        "plan_code": plan["code"],
        "price": float(plan["price"]),
        "gst_amount": payment_result["tax_amount"],
        "total_amount": payment_result["total_amount"],
        "validity_days": plan["validity_days"],
        "swaps_included": plan["swaps_included"],
        "payment_link": payment_result["payment_link"],
        "order_id": payment_result["order_id"],
        "sms_sent": sms_result.get("success", False),
        "expires_at": payment_result.get("expires_at"),
        "message": (
            f"Payment link for {plan['name']} (Rs.{payment_result['total_amount']:.0f}) sent to {phone_number}. "
            f"Link valid for 24 hours."
        ),
        "message_hi": (
            f"{plan.get('name_hi') or plan['name']} ke liye Rs.{payment_result['total_amount']:.0f} ka payment link "
            f"{phone_number} pe bhej diya hai. Link 24 ghante tak valid hai."
        )
    }


async def get_subscription_with_penalty(db: AsyncSession, phone_number: str) -> dict:
    """Get subscription status with any applicable penalties."""
    from .swap_service import get_penalty_details


    subscription = await get_subscription_status(db, phone_number)
    penalty = await get_penalty_details(db, phone_number)

    if penalty and penalty.get("has_penalty"):
        subscription["penalty"] = penalty
        subscription["has_penalty"] = True

        # Update message to include penalty
        if subscription.get("message"):
            subscription["message"] += f" Note: Penalty of Rs.{penalty['penalty_amount']:.0f} is applicable."
        if subscription.get("message_hi"):
            subscription["message_hi"] += f" Note: Rs.{penalty['penalty_amount']:.0f} ki penalty hai."
    else:
        subscription["penalty"] = None
        subscription["has_penalty"] = False

    return subscription