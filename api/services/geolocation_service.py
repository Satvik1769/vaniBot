"""Geolocation service for getting user location from IP/phone."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional, Tuple
import httpx
import os
import logging

logger = logging.getLogger(__name__)

# Google Geolocation API configuration
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
GOOGLE_GEOLOCATION_URL = "https://www.googleapis.com/geolocation/v1/geolocate"

# IP Geolocation fallback (ip-api.com is free)
IP_GEOLOCATION_URL = "http://ip-api.com/json"


async def get_location_from_ip(ip_address: str) -> Optional[dict]:
    """Get location from IP address using ip-api.com (free service)."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{IP_GEOLOCATION_URL}/{ip_address}",
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    return {
                        "latitude": data.get("lat"),
                        "longitude": data.get("lon"),
                        "city": data.get("city"),
                        "region": data.get("regionName"),
                        "country": data.get("country"),
                        "source": "ip_geolocation"
                    }
    except Exception as e:
        logger.error(f"IP geolocation error: {e}")

    return None


async def get_location_from_google(
    cell_towers: list = None,
    wifi_access_points: list = None,
    ip_address: str = None
) -> Optional[dict]:
    """Get location using Google Geolocation API."""
    if not GOOGLE_MAPS_API_KEY:
        logger.warning("Google Maps API key not configured")
        return None

    try:
        payload = {
            "considerIp": True if ip_address else False
        }

        if cell_towers:
            payload["cellTowers"] = cell_towers
        if wifi_access_points:
            payload["wifiAccessPoints"] = wifi_access_points

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GOOGLE_GEOLOCATION_URL}?key={GOOGLE_MAPS_API_KEY}",
                json=payload,
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                location = data.get("location", {})
                return {
                    "latitude": location.get("lat"),
                    "longitude": location.get("lng"),
                    "accuracy": data.get("accuracy"),
                    "source": "google_geolocation"
                }
            else:
                logger.error(f"Google Geolocation error: {response.text}")

    except Exception as e:
        logger.error(f"Google Geolocation error: {e}")

    return None


async def get_location_from_phone_number(
    db: AsyncSession,
    phone_number: str
) -> Optional[dict]:
    """Get location from user's registered city in database."""
    try:
        query = text("""
            SELECT city,
                   CASE city
                       WHEN 'Delhi' THEN 28.6139
                       WHEN 'New Delhi' THEN 28.6139
                       WHEN 'Noida' THEN 28.5355
                       WHEN 'Gurgaon' THEN 28.4595
                       WHEN 'Gurugram' THEN 28.4595
                       WHEN 'Mumbai' THEN 19.0760
                       WHEN 'Bangalore' THEN 12.9716
                       WHEN 'Bengaluru' THEN 12.9716
                       WHEN 'Hyderabad' THEN 17.3850
                       WHEN 'Chennai' THEN 13.0827
                       WHEN 'Kolkata' THEN 22.5726
                       WHEN 'Pune' THEN 18.5204
                       WHEN 'Jaipur' THEN 26.9124
                       WHEN 'Lucknow' THEN 26.8467
                       WHEN 'Ahmedabad' THEN 23.0225
                       ELSE 28.6139  -- Default to Delhi
                   END as latitude,
                   CASE city
                       WHEN 'Delhi' THEN 77.2090
                       WHEN 'New Delhi' THEN 77.2090
                       WHEN 'Noida' THEN 77.3910
                       WHEN 'Gurgaon' THEN 77.0266
                       WHEN 'Gurugram' THEN 77.0266
                       WHEN 'Mumbai' THEN 72.8777
                       WHEN 'Bangalore' THEN 77.5946
                       WHEN 'Bengaluru' THEN 77.5946
                       WHEN 'Hyderabad' THEN 78.4867
                       WHEN 'Chennai' THEN 80.2707
                       WHEN 'Kolkata' THEN 88.3639
                       WHEN 'Pune' THEN 73.8567
                       WHEN 'Jaipur' THEN 75.7873
                       WHEN 'Lucknow' THEN 80.9462
                       WHEN 'Ahmedabad' THEN 72.5714
                       ELSE 77.2090  -- Default to Delhi
                   END as longitude
            FROM drivers
            WHERE phone_number = :phone_number
        """)
        result = await db.execute(query, {"phone_number": phone_number})
        row = result.fetchone()

        if row:
            data = dict(row._mapping)
            return {
                "latitude": float(data["latitude"]),
                "longitude": float(data["longitude"]),
                "city": data["city"],
                "source": "database"
            }

    except Exception as e:
        logger.error(f"Database location lookup error: {e}")

    return None


async def get_user_location(
    db: AsyncSession,
    phone_number: str = None,
    ip_address: str = None,
    call_sid: str = None
) -> dict:
    """
    Get user location using multiple sources in order of preference:
    1. Call recording metadata (if call_sid provided)
    2. IP geolocation (if ip_address provided)
    3. User's registered city from database
    4. Default to Delhi
    """
    location = None

    # Try to get from call recording first
    if call_sid:
        try:
            query = text("""
                SELECT caller_latitude, caller_longitude
                FROM call_recordings
                WHERE call_sid = :call_sid
            """)
            result = await db.execute(query, {"call_sid": call_sid})
            row = result.fetchone()
            if row and row[0] and row[1]:
                location = {
                    "latitude": float(row[0]),
                    "longitude": float(row[1]),
                    "source": "call_metadata"
                }
        except Exception as e:
            logger.error(f"Error getting location from call: {e}")

    # Try IP geolocation
    if not location and ip_address:
        location = await get_location_from_ip(ip_address)

    # Try database lookup
    if not location and phone_number:
        location = await get_location_from_phone_number(db, phone_number)

    # Default to Delhi if no location found
    if not location:
        location = {
            "latitude": 28.6139,
            "longitude": 77.2090,
            "city": "Delhi",
            "source": "default"
        }

    return location


async def save_caller_location(
    db: AsyncSession,
    call_sid: str,
    latitude: float,
    longitude: float
):
    """Save caller location to call recording."""
    try:
        query = text("""
            UPDATE call_recordings
            SET caller_latitude = :latitude, caller_longitude = :longitude
            WHERE call_sid = :call_sid
        """)
        await db.execute(query, {
            "call_sid": call_sid,
            "latitude": latitude,
            "longitude": longitude
        })
        await db.commit()
    except Exception as e:
        logger.error(f"Error saving caller location: {e}")


async def get_nearest_stations(
    db: AsyncSession,
    latitude: float,
    longitude: float,
    limit: int = 5,
    is_dsk: bool = False,
    min_available_batteries: int = 0
) -> list:
    """Get nearest stations sorted by distance."""
    try:
        dsk_condition = "AND s.is_dsk = true" if is_dsk else ""
        battery_condition = f"AND COALESCE(si.available_batteries, 0) >= {min_available_batteries}" if min_available_batteries > 0 else ""

        query = text(f"""
            SELECT
                s.id, s.code, s.name, s.address, s.landmark,
                s.latitude, s.longitude, s.city, s.operating_hours,
                s.contact_phone, s.is_dsk, s.google_map_url,
                COALESCE(si.available_batteries, 0) as available_batteries,
                COALESCE(si.charging_batteries, 0) as charging_batteries,
                COALESCE(si.total_slots, 0) as total_slots,
                calculate_distance(:lat, :lon, s.latitude, s.longitude) as distance_km
            FROM stations s
            LEFT JOIN station_inventory si ON s.id = si.station_id
            WHERE s.is_active = true
            {dsk_condition}
            {battery_condition}
            ORDER BY distance_km ASC
            LIMIT :limit
        """)

        result = await db.execute(query, {
            "lat": latitude,
            "lon": longitude,
            "limit": limit
        })
        rows = result.fetchall()

        stations = []
        for row in rows:
            data = dict(row._mapping)
            data["distance_km"] = round(float(data["distance_km"]), 2)

            # Generate Google Maps URL if not present
            if not data.get("google_map_url"):
                data["google_map_url"] = (
                    f"https://www.google.com/maps/dir/?api=1&destination="
                    f"{data['latitude']},{data['longitude']}"
                )

            stations.append(data)

        return stations

    except Exception as e:
        logger.error(f"Error getting nearest stations: {e}")
        return []


async def get_nearest_dsk(
    db: AsyncSession,
    latitude: float,
    longitude: float,
    limit: int = 3
) -> list:
    """Get nearest DSK (Dealer Service Kiosk) locations."""
    return await get_nearest_stations(
        db=db,
        latitude=latitude,
        longitude=longitude,
        limit=limit,
        is_dsk=True
    )