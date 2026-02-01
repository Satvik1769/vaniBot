"""Swap and invoice service for database operations."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List, Optional
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

# Penalty configuration
PENALTY_GRACE_DAYS = 4  # Days after end_date before penalty starts
PENALTY_DAILY_RATE = Decimal("80.00")  # Rs 80 per day


async def get_swap_history(
    db: AsyncSession,
    phone_number: str,
    time_period: str = "all",
    start_date: date = None,
    end_date: date = None,
    limit: int = 20
) -> dict:
    """Get driver's swap history."""
    # Calculate date range based on time_period
    today = date.today()
    if time_period == "today":
        start = today
        end = today
    elif time_period == "yesterday":
        start = today - timedelta(days=1)
        end = today - timedelta(days=1)
    elif time_period == "last_3_days":
        start = today - timedelta(days=3)
        end = today
    elif time_period == "last_week" or time_period == "last_7_days":
        start = today - timedelta(days=7)
        end = today
    elif time_period == "this_week":
        # Start from Monday of current week
        start = today - timedelta(days=today.weekday())
        end = today
    elif time_period == "last_month" or time_period == "last_30_days":
        start = today - timedelta(days=30)
        end = today
    elif time_period == "this_month":
        start = today.replace(day=1)
        end = today
    elif time_period == "last_year" or time_period == "last_365_days":
        start = today - timedelta(days=365)
        end = today
    elif time_period == "this_year":
        start = today.replace(month=1, day=1)
        end = today
    elif time_period == "all":
        start = date(2020, 1, 1)
        end = today
    elif time_period == "custom" and start_date and end_date:
        start = start_date
        end = end_date
    else:
        # If time_period is a number like "3" (for last N days), handle it
        try:
            days = int(time_period)
            start = today - timedelta(days=days)
            end = today
        except (ValueError, TypeError):
            start = start_date or today
            end = end_date or today

    query = text("""
        SELECT
            sw.id, sw.driver_id, sw.station_id, sw.subscription_id,
            sw.old_battery_id, sw.new_battery_id,
            sw.old_battery_charge_level, sw.new_battery_charge_level,
            sw.swap_time, sw.is_subscription_swap, sw.charge_amount, sw.status,
            s.name as station_name, s.code as station_code,
            i.invoice_number,
            d.driver_name as driver_name
        FROM swaps sw
        JOIN drivers d ON sw.driver_id = d.id
        JOIN stations s ON sw.station_id = s.id
        LEFT JOIN invoices i ON sw.id = i.swap_id
        WHERE d.phone_number = :phone_number
        AND DATE(sw.swap_time) BETWEEN :start_date AND :end_date
        ORDER BY sw.swap_time DESC
        LIMIT :limit
    """)
    result = await db.execute(query, {
        "phone_number": phone_number,
        "start_date": start,
        "end_date": end,
        "limit": limit
    })
    rows = result.fetchall()
    logging.error(rows)
    swaps = [dict(row._mapping) for row in rows]

    # Calculate totals
    total_charged = sum(s["charge_amount"] for s in swaps)
    total_free = sum(1 for s in swaps if s["charge_amount"] == 0)

    # Generate messages
    if swaps:
        driver_name = swaps[0]["driver_name"]
        if time_period == "today":
            msg = f"Today you made {len(swaps)} swaps."
            msg_hi = f"Aaj aapne {len(swaps)} swaps kiye hain."
        else:
            msg = f"Found {len(swaps)} swaps in the selected period."
            msg_hi = f"Selected period mein {len(swaps)} swaps mile."

        if total_charged > 0:
            msg += f" Total charged: Rs.{total_charged}"
            msg_hi += f" Total charge: Rs.{total_charged}"
    else:
        driver_name = None
        msg = "No swaps found for the selected period."
        msg_hi = "Selected period mein koi swap nahi mila."

    # Get driver_id from first swap or query
    driver_id = swaps[0]["driver_id"] if swaps else None
    if not driver_id:
        driver_query = text("SELECT id FROM drivers WHERE phone_number = :phone")
        driver_result = await db.execute(driver_query, {"phone": phone_number})
        driver_row = driver_result.fetchone()
        driver_id = driver_row[0] if driver_row else None

    return {
        "driver_id": driver_id,
        "driver_name": driver_name,
        "phone_number": phone_number,
        "time_period": time_period,
        "swaps": swaps,
        "total_swaps": len(swaps),
        "total_charged": total_charged,
        "total_free": total_free,
        "message": msg,
        "message_hi": msg_hi
    }


async def get_invoice_details(
    db: AsyncSession,
    phone_number: str,
    invoice_number: str = None,
    swap_id: str = None,
    invoice_date: date = None
) -> Optional[dict]:
    """Get invoice details with explanation."""
    conditions = ["d.phone_number = :phone_number"]
    params = {"phone_number": phone_number}

    if invoice_number:
        conditions.append("i.invoice_number = :invoice_number")
        params["invoice_number"] = invoice_number
    elif swap_id:
        conditions.append("i.swap_id = :swap_id")
        params["swap_id"] = swap_id
    elif invoice_date:
        conditions.append("DATE(i.generated_at) = :invoice_date")
        params["invoice_date"] = invoice_date
    else:
        # Get most recent invoice
        conditions.append("1=1")

    query = text(f"""
        SELECT
            i.id, i.invoice_number, i.driver_id, i.swap_id, i.subscription_id,
            i.invoice_type, i.amount, i.tax_amount, i.total_amount,
            i.description, i.description_hi, i.payment_status, i.generated_at,
            d.name as driver_name,
            sw.swap_time, sw.is_subscription_swap, sw.charge_amount,
            sw.old_battery_id, sw.new_battery_id,
            st.name as station_name, st.code as station_code,
            sp.name as plan_name, sp.swaps_included
        FROM invoices i
        JOIN drivers d ON i.driver_id = d.id
        LEFT JOIN swaps sw ON i.swap_id = sw.id
        LEFT JOIN stations st ON sw.station_id = st.id
        LEFT JOIN driver_subscriptions ds ON i.subscription_id = ds.id
        LEFT JOIN subscription_plans sp ON ds.plan_id = sp.id
        WHERE {' AND '.join(conditions)}
        ORDER BY i.generated_at DESC
        LIMIT 1
    """)
    result = await db.execute(query, params)
    row = result.fetchone()

    if not row:
        return None

    data = dict(row._mapping)

    # Generate explanation based on invoice type
    if data["invoice_type"] == "extra_swap":
        explanation = (
            f"This charge of Rs.{data['amount']} was for an extra swap beyond your daily plan limit. "
            f"Your plan includes {data['swaps_included']} swaps per day. "
            f"This was an additional swap at {data['station_name']}."
        )
        explanation_hi = (
            f"Yeh Rs.{data['amount']} ka charge aapke daily plan ki limit ke baad ke swap ke liye laga. "
            f"Aapke plan mein {data['swaps_included']} swaps per day included hain. "
            f"Yeh {data['station_name']} pe additional swap tha."
        )
        breakdown = [
            {"item": "Extra Swap Charge", "item_hi": "Extra Swap Charge", "amount": data["amount"]},
            {"item": "GST (18%)", "item_hi": "GST (18%)", "amount": data["tax_amount"]},
            {"item": "Total", "item_hi": "Kul", "amount": data["total_amount"]}
        ]
    elif data["invoice_type"] == "subscription":
        explanation = (
            f"This is your subscription payment for {data['plan_name']} plan."
        )
        explanation_hi = (
            f"Yeh aapka {data['plan_name']} plan ka subscription payment hai."
        )
        breakdown = [
            {"item": f"{data['plan_name']} Plan", "item_hi": f"{data['plan_name']} Plan", "amount": data["amount"]},
            {"item": "GST (18%)", "item_hi": "GST (18%)", "amount": data["tax_amount"]},
            {"item": "Total", "item_hi": "Kul", "amount": data["total_amount"]}
        ]
    else:
        explanation = f"Invoice for {data['invoice_type']}"
        explanation_hi = f"{data['invoice_type']} ke liye invoice"
        breakdown = [
            {"item": "Amount", "item_hi": "Rashi", "amount": data["amount"]},
            {"item": "Tax", "item_hi": "Tax", "amount": data["tax_amount"]},
            {"item": "Total", "item_hi": "Kul", "amount": data["total_amount"]}
        ]

    return {
        "invoice": {
            "id": data["id"],
            "invoice_number": data["invoice_number"],
            "driver_id": data["driver_id"],
            "swap_id": data["swap_id"],
            "subscription_id": data["subscription_id"],
            "invoice_type": data["invoice_type"],
            "amount": data["amount"],
            "tax_amount": data["tax_amount"],
            "total_amount": data["total_amount"],
            "description": data["description"],
            "description_hi": data["description_hi"],
            "payment_status": data["payment_status"],
            "generated_at": data["generated_at"]
        },
        "explanation": explanation,
        "explanation_hi": explanation_hi,
        "breakdown": breakdown,
        "related_swap": {
            "swap_time": data["swap_time"],
            "station_name": data["station_name"],
            "station_code": data["station_code"],
            "old_battery_id": data["old_battery_id"],
            "new_battery_id": data["new_battery_id"]
        } if data["swap_id"] else None
    }


async def get_penalty_details(
    db: AsyncSession,
    phone_number: str
) -> Optional[dict]:
    """Get penalty details for unreturned battery."""
    query = text("""
        SELECT
            ds.id as subscription_id,
            ds.driver_id,
            ds.end_date,
            ds.battery_id,
            ds.battery_returned,
            ds.battery_returned_date,
            d.name as driver_name,
            d.phone_number,
            sp.name as plan_name,
            CASE
                WHEN ds.battery_returned = false
                     AND ds.end_date < CURRENT_DATE - INTERVAL '4 days'
                THEN true
                ELSE false
            END as has_penalty,
            CASE
                WHEN ds.battery_returned = false
                     AND ds.end_date < CURRENT_DATE - INTERVAL '4 days'
                THEN (CURRENT_DATE - ds.end_date - 4)
                ELSE 0
            END as days_overdue
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

    if not row:
        return None

    data = dict(row._mapping)

    if not data["has_penalty"]:
        return {
            "has_penalty": False,
            "driver_name": data["driver_name"],
            "battery_id": data["battery_id"],
            "battery_returned": data["battery_returned"],
            "end_date": data["end_date"],
            "message": "No penalty applicable. Battery was returned on time.",
            "message_hi": "Koi penalty nahi hai. Battery samay pe return ho gayi thi."
        }

    days_overdue = int(data["days_overdue"])
    penalty_amount = float(PENALTY_DAILY_RATE * days_overdue)

    return {
        "has_penalty": True,
        "subscription_id": str(data["subscription_id"]),
        "driver_id": str(data["driver_id"]),
        "driver_name": data["driver_name"],
        "battery_id": data["battery_id"],
        "battery_returned": data["battery_returned"],
        "end_date": data["end_date"],
        "days_overdue": days_overdue,
        "daily_rate": float(PENALTY_DAILY_RATE),
        "penalty_amount": penalty_amount,
        "message": (
            f"Penalty of Rs.{penalty_amount:.0f} applicable. "
            f"Battery not returned for {days_overdue} days after grace period. "
            f"Daily penalty rate is Rs.{PENALTY_DAILY_RATE}/day after {PENALTY_GRACE_DAYS} days past subscription end."
        ),
        "message_hi": (
            f"Rs.{penalty_amount:.0f} ki penalty lagi hai. "
            f"Battery grace period ke baad {days_overdue} din se return nahi hui. "
            f"Subscription khatam hone ke {PENALTY_GRACE_DAYS} din baad Rs.{PENALTY_DAILY_RATE}/din penalty lagti hai."
        ),
        "breakdown": [
            {
                "item": f"Late return penalty ({days_overdue} days x Rs.{PENALTY_DAILY_RATE})",
                "item_hi": f"Late return penalty ({days_overdue} din x Rs.{PENALTY_DAILY_RATE})",
                "amount": penalty_amount
            }
        ]
    }


async def get_invoice_with_penalty(
    db: AsyncSession,
    phone_number: str,
    invoice_number: str = None,
    time_period: str = None
) -> dict:
    """Get invoice details with penalty information if applicable."""
    # Get invoice details
    invoice_result = await get_invoice_details(db, phone_number, invoice_number)

    # Get penalty details
    penalty_result = await get_penalty_details(db, phone_number)

    combined_breakdown = []
    total_amount = Decimal("0")

    if invoice_result:
        combined_breakdown.extend(invoice_result.get("breakdown", []))
        total_amount += Decimal(str(invoice_result.get("invoice", {}).get("total_amount", 0)))

    if penalty_result and penalty_result.get("has_penalty"):
        combined_breakdown.extend(penalty_result.get("breakdown", []))
        total_amount += Decimal(str(penalty_result.get("penalty_amount", 0)))

    # Generate combined explanation
    if invoice_result and penalty_result and penalty_result.get("has_penalty"):
        explanation = (
            f"{invoice_result.get('explanation', '')} "
            f"Additionally, {penalty_result.get('message', '')}"
        )
        explanation_hi = (
            f"{invoice_result.get('explanation_hi', '')} "
            f"Saath hi, {penalty_result.get('message_hi', '')}"
        )
    elif invoice_result:
        explanation = invoice_result.get("explanation", "")
        explanation_hi = invoice_result.get("explanation_hi", "")
    elif penalty_result:
        explanation = penalty_result.get("message", "")
        explanation_hi = penalty_result.get("message_hi", "")
    else:
        explanation = "No invoice or penalty found."
        explanation_hi = "Koi invoice ya penalty nahi mili."

    return {
        "invoice": invoice_result.get("invoice") if invoice_result else None,
        "penalty": penalty_result if penalty_result and penalty_result.get("has_penalty") else None,
        "breakdown": combined_breakdown,
        "total_amount": float(total_amount),
        "explanation": explanation,
        "explanation_hi": explanation_hi,
        "has_penalty": penalty_result.get("has_penalty", False) if penalty_result else False
    }