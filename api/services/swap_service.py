"""Swap and invoice service for database operations."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List, Optional
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID


async def get_swap_history(
    db: AsyncSession,
    phone_number: str,
    time_period: str = "today",
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
    elif time_period == "last_week":
        start = today - timedelta(days=7)
        end = today
    elif time_period == "last_month":
        start = today - timedelta(days=30)
        end = today
    elif time_period == "all":
        start = date(2020, 1, 1)
        end = today
    else:
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
            d.name as driver_name
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