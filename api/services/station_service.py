"""Station service for database operations."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List, Optional
from decimal import Decimal


async def get_nearest_stations(
    db: AsyncSession,
    latitude: Decimal,
    longitude: Decimal,
    limit: int = 5,
    max_distance_km: float = 10.0
) -> List[dict]:
    """Get nearest stations with availability."""
    query = text("""
        SELECT
            s.id, s.code, s.name, s.address, s.landmark,
            s.latitude, s.longitude, s.city, s.pincode,
            s.operating_hours, s.contact_phone, s.is_active,
            si.available_batteries, si.charging_batteries,
            si.total_slots, si.last_updated,
            calculate_distance(:lat, :lon, s.latitude, s.longitude) as distance_km
        FROM stations s
        LEFT JOIN station_inventory si ON s.id = si.station_id
        WHERE s.is_active = true
        AND calculate_distance(:lat, :lon, s.latitude, s.longitude) <= :max_distance
        ORDER BY distance_km ASC
        LIMIT :limit
    """)
    result = await db.execute(query, {
        "lat": latitude,
        "lon": longitude,
        "max_distance": max_distance_km,
        "limit": limit
    })
    rows = result.fetchall()
    return [dict(row._mapping) for row in rows]


async def get_stations_by_city(db: AsyncSession, city: str, limit: int = 10) -> List[dict]:
    """Get stations in a city."""
    query = text("""
        SELECT
            s.id, s.code, s.name, s.address, s.landmark,
            s.latitude, s.longitude, s.city, s.pincode,
            s.operating_hours, s.contact_phone, s.is_active,
            si.available_batteries, si.charging_batteries,
            si.total_slots, si.last_updated
        FROM stations s
        LEFT JOIN station_inventory si ON s.id = si.station_id
        WHERE s.is_active = true
        AND LOWER(s.city) LIKE LOWER(:city)
        ORDER BY si.available_batteries DESC NULLS LAST
        LIMIT :limit
    """)
    result = await db.execute(query, {"city": f"%{city}%", "limit": limit})
    rows = result.fetchall()
    return [dict(row._mapping) for row in rows]


async def search_stations(db: AsyncSession, search_term: str, limit: int = 5) -> List[dict]:
    """Search stations by name, code, or location."""
    query = text("""
        SELECT
            s.id, s.code, s.name, s.address, s.landmark,
            s.latitude, s.longitude, s.city, s.pincode,
            s.operating_hours, s.contact_phone, s.is_active,
            si.available_batteries, si.charging_batteries,
            si.total_slots, si.last_updated
        FROM stations s
        LEFT JOIN station_inventory si ON s.id = si.station_id
        WHERE s.is_active = true
        AND (
            LOWER(s.name) LIKE LOWER(:term)
            OR LOWER(s.code) LIKE LOWER(:term)
            OR LOWER(s.address) LIKE LOWER(:term)
            OR LOWER(s.landmark) LIKE LOWER(:term)
            OR LOWER(s.city) LIKE LOWER(:term)
        )
        ORDER BY si.available_batteries DESC NULLS LAST
        LIMIT :limit
    """)
    result = await db.execute(query, {"term": f"%{search_term}%", "limit": limit})
    rows = result.fetchall()
    return [dict(row._mapping) for row in rows]


async def get_station_availability(
    db: AsyncSession,
    station_id: str = None,
    station_code: str = None,
    station_name: str = None
) -> Optional[dict]:
    """Get detailed station availability."""
    conditions = []
    params = {}

    if station_id:
        conditions.append("s.id = :station_id")
        params["station_id"] = station_id
    elif station_code:
        conditions.append("LOWER(s.code) = LOWER(:station_code)")
        params["station_code"] = station_code
    elif station_name:
        conditions.append("LOWER(s.name) LIKE LOWER(:station_name)")
        params["station_name"] = f"%{station_name}%"
    else:
        return None

    query = text(f"""
        SELECT
            s.id, s.code, s.name, s.address, s.landmark,
            s.latitude, s.longitude, s.city, s.pincode,
            s.operating_hours, s.contact_phone, s.is_active,
            COALESCE(si.available_batteries, 0) as available_batteries,
            COALESCE(si.charging_batteries, 0) as charging_batteries,
            COALESCE(si.total_slots, 0) as total_slots,
            si.last_updated
        FROM stations s
        LEFT JOIN station_inventory si ON s.id = si.station_id
        WHERE s.is_active = true AND {' AND '.join(conditions)}
        LIMIT 1
    """)
    result = await db.execute(query, params)
    row = result.fetchone()
    if row:
        data = dict(row._mapping)
        available = data["available_batteries"]
        total = data["total_slots"]

        # Calculate status
        if available > 10:
            status = "high"
            status_msg = f"Good availability - {available} batteries ready"
            status_msg_hi = f"Achhi availability - {available} battery ready hain"
        elif available >= 5:
            status = "medium"
            status_msg = f"Moderate availability - {available} batteries ready"
            status_msg_hi = f"Thik availability - {available} battery ready hain"
        else:
            status = "low"
            status_msg = f"Low availability - only {available} batteries"
            status_msg_hi = f"Kam availability - sirf {available} battery hain"

        data["status"] = status
        data["status_message"] = status_msg
        data["status_message_hi"] = status_msg_hi
        data["occupancy_percentage"] = (total - available) / total * 100 if total > 0 else 0
        return data
    return None