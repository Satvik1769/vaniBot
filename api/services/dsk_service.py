"""DSK and leave service for database operations."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List, Optional
from datetime import date
from decimal import Decimal


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