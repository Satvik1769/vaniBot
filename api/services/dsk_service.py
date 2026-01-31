"""DSK and leave service for database operations."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal

# Leave balance constants
MAX_LEAVES_PER_MONTH = 4


async def get_leave_balance(db: AsyncSession, phone_number: str) -> dict:
    """Get current month's leave balance for driver."""
    current_month = datetime.now().strftime("%Y-%m")

    # Get driver
    driver_query = text("SELECT id, driver_name FROM drivers WHERE phone_number = :phone")
    driver_result = await db.execute(driver_query, {"phone": phone_number})
    driver_row = driver_result.fetchone()

    if not driver_row:
        return {
            "found": False,
            "message": "Driver not found.",
            "message_hi": "Driver nahi mila."
        }

    driver_id = driver_row[0]
    driver_name = driver_row[1]

    # Get or create leave balance for current month
    balance_query = text("""
        SELECT id, total_leaves, used_leaves, remaining_leaves
        FROM leave_balance
        WHERE driver_id = :driver_id AND month_year = :month_year
    """)
    balance_result = await db.execute(balance_query, {
        "driver_id": driver_id,
        "month_year": current_month
    })
    balance_row = balance_result.fetchone()

    if balance_row:
        data = dict(balance_row._mapping)
    else:
        # Create new leave balance for this month
        create_query = text("""
            INSERT INTO leave_balance (driver_id, month_year, total_leaves, used_leaves)
            VALUES (:driver_id, :month_year, :total_leaves, 0)
            RETURNING id, total_leaves, used_leaves
        """)
        create_result = await db.execute(create_query, {
            "driver_id": driver_id,
            "month_year": current_month,
            "total_leaves": MAX_LEAVES_PER_MONTH
        })
        await db.commit()
        create_row = create_result.fetchone()
        data = dict(create_row._mapping)
        data["remaining_leaves"] = MAX_LEAVES_PER_MONTH

    remaining = data.get("remaining_leaves", MAX_LEAVES_PER_MONTH - data.get("used_leaves", 0))

    return {
        "found": True,
        "driver_id": str(driver_id),
        "driver_name": driver_name,
        "month": current_month,
        "total_leaves": data.get("total_leaves", MAX_LEAVES_PER_MONTH),
        "used_leaves": data.get("used_leaves", 0),
        "remaining_leaves": remaining,
        "message": f"You have {remaining} leaves remaining this month out of {MAX_LEAVES_PER_MONTH}.",
        "message_hi": f"Is mahine aapke paas {MAX_LEAVES_PER_MONTH} mein se {remaining} leaves bachi hain."
    }


async def use_leave(db: AsyncSession, phone_number: str, days: int = 1) -> dict:
    """Use leave from balance when applying leave."""
    balance = await get_leave_balance(db, phone_number)

    if not balance.get("found"):
        return balance

    if balance["remaining_leaves"] < days:
        return {
            "success": False,
            "remaining_leaves": balance["remaining_leaves"],
            "message": f"Not enough leaves. You have {balance['remaining_leaves']} remaining, but need {days}.",
            "message_hi": f"Aapke paas {balance['remaining_leaves']} leaves hain, lekin {days} chahiye."
        }

    current_month = datetime.now().strftime("%Y-%m")

    # Update leave balance
    update_query = text("""
        UPDATE leave_balance
        SET used_leaves = used_leaves + :days, updated_at = NOW()
        WHERE driver_id = :driver_id AND month_year = :month_year
        RETURNING used_leaves
    """)
    await db.execute(update_query, {
        "driver_id": balance["driver_id"],
        "month_year": current_month,
        "days": days
    })
    await db.commit()

    new_remaining = balance["remaining_leaves"] - days
    return {
        "success": True,
        "used": days,
        "remaining_leaves": new_remaining,
        "message": f"Used {days} leave(s). {new_remaining} remaining this month.",
        "message_hi": f"{days} leave use ki. Is mahine {new_remaining} bachi hain."
    }


async def get_nearest_dsk(
    db: AsyncSession,
    latitude: Decimal = None,
    longitude: Decimal = None,
    city: str = None,
    service_type: str = None,
    limit: int = 3
) -> List[dict]:
    """Get nearest DSK locations."""
    conditions = ["d.is_active = true"]
    params = {"limit": limit}

    if service_type:
        conditions.append(":service_type = ANY(d.services)")
        params["service_type"] = service_type

    if latitude and longitude:
        query = text(f"""
            SELECT
                d.id, d.code, d.name, d.address, d.landmark,
                d.latitude, d.longitude, d.city, d.pincode,
                d.phone, d.operating_hours, d.services, d.is_active,
                calculate_distance(:lat, :lon, d.latitude, d.longitude) as distance_km
            FROM dsk_locations d
            WHERE {' AND '.join(conditions)}
            ORDER BY distance_km ASC
            LIMIT :limit
        """)
        params["lat"] = latitude
        params["lon"] = longitude
    elif city:
        conditions.append("LOWER(d.city) LIKE LOWER(:city)")
        params["city"] = f"%{city}%"
        query = text(f"""
            SELECT
                d.id, d.code, d.name, d.address, d.landmark,
                d.latitude, d.longitude, d.city, d.pincode,
                d.phone, d.operating_hours, d.services, d.is_active,
                NULL as distance_km
            FROM dsk_locations d
            WHERE {' AND '.join(conditions)}
            LIMIT :limit
        """)
    else:
        query = text(f"""
            SELECT
                d.id, d.code, d.name, d.address, d.landmark,
                d.latitude, d.longitude, d.city, d.pincode,
                d.phone, d.operating_hours, d.services, d.is_active,
                NULL as distance_km
            FROM dsk_locations d
            WHERE {' AND '.join(conditions)}
            LIMIT :limit
        """)

    result = await db.execute(query, params)
    rows = result.fetchall()
    return [dict(row._mapping) for row in rows]


async def get_activation_info(db: AsyncSession, city: str = None) -> dict:
    """Get activation information and nearest DSK."""
    dsk_list = await get_nearest_dsk(db, city=city, service_type="activation", limit=1)
    nearest_dsk = dsk_list[0] if dsk_list else None

    required_docs = [
        "Aadhaar Card (Original + Photocopy)",
        "Driving License (Original + Photocopy)",
        "Passport Size Photo (2 copies)",
        "Vehicle RC (if applicable)"
    ]
    required_docs_hi = [
        "Aadhaar Card (Original + Photocopy)",
        "Driving License (Original + Photocopy)",
        "Passport Size Photo (2 copies)",
        "Vehicle RC (agar applicable ho)"
    ]

    process_steps = [
        "Visit nearest DSK with required documents",
        "Complete KYC verification",
        "Select your subscription plan",
        "Pay via UPI/Card/Cash",
        "Collect your first charged battery",
        "Start riding!"
    ]
    process_steps_hi = [
        "Required documents ke saath nearest DSK jayein",
        "KYC verification complete karein",
        "Apna subscription plan select karein",
        "UPI/Card/Cash se payment karein",
        "Apni pehli charged battery collect karein",
        "Riding shuru karein!"
    ]

    return {
        "nearest_dsk": nearest_dsk,
        "required_documents": required_docs,
        "required_documents_hi": required_docs_hi,
        "process_steps": process_steps,
        "process_steps_hi": process_steps_hi,
        "estimated_time": "15-20 minutes",
        "estimated_time_hi": "15-20 minute",
        "contact_number": "1800-123-4567",
        "message": "Visit your nearest DSK to activate your Battery Smart account.",
        "message_hi": "Apna Battery Smart account activate karne ke liye nearest DSK jayein."
    }


async def apply_leave(
    db: AsyncSession,
    phone_number: str,
    start_date: date,
    end_date: date,
    reason: str = None
) -> Optional[dict]:
    """Apply for leave."""
    # Get driver
    driver_query = text("SELECT id FROM drivers WHERE phone_number = :phone")
    driver_result = await db.execute(driver_query, {"phone": phone_number})
    driver_row = driver_result.fetchone()
    if not driver_row:
        return None

    driver_id = driver_row[0]
    days = (end_date - start_date).days + 1

    # Create leave request
    query = text("""
        INSERT INTO driver_leaves (driver_id, start_date, end_date, reason, status)
        VALUES (:driver_id, :start_date, :end_date, :reason, 'pending')
        RETURNING id, start_date, end_date, reason, status
    """)
    result = await db.execute(query, {
        "driver_id": driver_id,
        "start_date": start_date,
        "end_date": end_date,
        "reason": reason
    })
    await db.commit()
    row = result.fetchone()

    if row:
        data = dict(row._mapping)
        return {
            "id": data["id"],
            "driver_id": driver_id,
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "days": days,
            "reason": data["reason"],
            "status": data["status"],
            "message": f"Leave request submitted for {days} days ({start_date} to {end_date}). Status: Pending approval.",
            "message_hi": f"{days} din ki leave request submit ho gayi ({start_date} se {end_date}). Status: Approval pending."
        }
    return None


async def get_leave_status(db: AsyncSession, phone_number: str) -> dict:
    """Get leave status for driver."""
    # Get driver
    driver_query = text("""
        SELECT id, name FROM drivers WHERE phone_number = :phone
    """)
    driver_result = await db.execute(driver_query, {"phone": phone_number})
    driver_row = driver_result.fetchone()
    if not driver_row:
        return {
            "driver_id": None,
            "driver_name": None,
            "phone_number": phone_number,
            "pending_leaves": [],
            "approved_leaves": [],
            "total_pending": 0,
            "total_approved": 0,
            "message": "Driver not found.",
            "message_hi": "Driver nahi mila."
        }

    driver_id = driver_row[0]
    driver_name = driver_row[1]

    # Get pending leaves
    pending_query = text("""
        SELECT id, driver_id, start_date, end_date, reason, status
        FROM driver_leaves
        WHERE driver_id = :driver_id AND status = 'pending'
        ORDER BY start_date ASC
    """)
    pending_result = await db.execute(pending_query, {"driver_id": driver_id})
    pending_rows = pending_result.fetchall()
    pending_leaves = []
    for row in pending_rows:
        data = dict(row._mapping)
        days = (data["end_date"] - data["start_date"]).days + 1
        pending_leaves.append({
            "id": data["id"],
            "driver_id": data["driver_id"],
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "days": days,
            "reason": data["reason"],
            "status": data["status"],
            "message": f"Leave from {data['start_date']} to {data['end_date']}",
            "message_hi": f"{data['start_date']} se {data['end_date']} tak leave"
        })

    # Get approved leaves
    approved_query = text("""
        SELECT id, driver_id, start_date, end_date, reason, status
        FROM driver_leaves
        WHERE driver_id = :driver_id AND status = 'approved'
        AND end_date >= CURRENT_DATE
        ORDER BY start_date ASC
    """)
    approved_result = await db.execute(approved_query, {"driver_id": driver_id})
    approved_rows = approved_result.fetchall()
    approved_leaves = []
    for row in approved_rows:
        data = dict(row._mapping)
        days = (data["end_date"] - data["start_date"]).days + 1
        approved_leaves.append({
            "id": data["id"],
            "driver_id": data["driver_id"],
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "days": days,
            "reason": data["reason"],
            "status": data["status"],
            "message": f"Leave from {data['start_date']} to {data['end_date']}",
            "message_hi": f"{data['start_date']} se {data['end_date']} tak leave"
        })

    total_pending = len(pending_leaves)
    total_approved = len(approved_leaves)

    if total_pending == 0 and total_approved == 0:
        msg = "No leave requests found."
        msg_hi = "Koi leave request nahi mili."
    else:
        msg = f"You have {total_pending} pending and {total_approved} approved leaves."
        msg_hi = f"Aapke {total_pending} pending aur {total_approved} approved leaves hain."

    return {
        "driver_id": driver_id,
        "driver_name": driver_name,
        "phone_number": phone_number,
        "pending_leaves": pending_leaves,
        "approved_leaves": approved_leaves,
        "total_pending": total_pending,
        "total_approved": total_approved,
        "message": msg,
        "message_hi": msg_hi
    }