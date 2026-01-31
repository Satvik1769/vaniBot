"""Custom actions for station finder and availability."""
from typing import Any, Dict, List, Text
import httpx
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

API_BASE_URL = "http://localhost:8000/api/v1"


class ActionFindNearestStations(Action):
    """Find nearest stations based on user location or phone number."""

    def name(self) -> Text:
        return "action_find_nearest_stations"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        location = tracker.get_slot("user_location")
        latitude = tracker.get_slot("user_latitude")
        longitude = tracker.get_slot("user_longitude")
        phone_number = tracker.get_slot("driver_phone")

        try:
            async with httpx.AsyncClient() as client:
                # Priority 1: Use coordinates if available
                if latitude and longitude:
                    response = await client.get(
                        f"{API_BASE_URL}/stations/nearest",
                        params={
                            "latitude": latitude,
                            "longitude": longitude,
                            "limit": 5
                        }
                    )
                # Priority 2: Use phone number for geolocation lookup
                elif phone_number:
                    response = await client.get(
                        f"{API_BASE_URL}/stations/nearest-by-phone/{phone_number}",
                        params={"limit": 5, "min_batteries": 1}
                    )
                # Priority 3: Search by location name
                elif location:
                    response = await client.get(
                        f"{API_BASE_URL}/stations/search",
                        params={"q": location, "limit": 5}
                    )
                else:
                    dispatcher.utter_message(
                        text="Kripya apna location batayein taaki main nearby stations dhundh sakun."
                    )
                    return []

                if response.status_code == 200:
                    data = response.json()
                    stations = data.get("stations", [])
                    user_location = data.get("user_location", {})

                    if not stations:
                        msg = f"{location or 'Aapke area'} ke paas koi station nahi mila. Kripya koi aur area try karein."
                        dispatcher.utter_message(text=msg)
                        return []

                    # Format station list
                    station_list_text = ""
                    for i, station in enumerate(stations[:5], 1):
                        name = station.get("name", "Unknown")
                        available = station.get("available_batteries", 0)
                        distance = station.get("distance_km")

                        if distance:
                            station_list_text += f"{i}. {name} - {distance:.1f} km - {available} batteries\n"
                        else:
                            station_list_text += f"{i}. {name} - {available} batteries available\n"

                    nearest = stations[0]

                    # Include Google Maps URL for first station
                    maps_url = nearest.get("google_map_url", "")
                    if maps_url:
                        station_list_text += f"\nDirections: {maps_url}"

                    return [
                        SlotSet("nearest_stations", stations),
                        SlotSet("station_list", station_list_text),
                        SlotSet("station_count", len(stations)),
                        SlotSet("nearest_station_name", nearest.get("name")),
                        SlotSet("nearest_station_address", nearest.get("address")),
                        SlotSet("available_batteries", nearest.get("available_batteries", 0)),
                        SlotSet("google_maps_url", maps_url),
                        SlotSet("user_latitude", user_location.get("latitude")),
                        SlotSet("user_longitude", user_location.get("longitude"))
                    ]
                else:
                    dispatcher.utter_message(
                        text="Stations dhundhne mein problem hui. Thodi der baad try karein."
                    )
                    return []

        except Exception as e:
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []


class ActionCheckStationAvailability(Action):
    """Check battery availability at a specific station."""

    def name(self) -> Text:
        return "action_check_station_availability"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        station_identifier = tracker.get_slot("station_identifier")
        nearest_stations = tracker.get_slot("nearest_stations")

        # If no specific station mentioned, use the first from nearest list
        if not station_identifier and nearest_stations:
            station_identifier = nearest_stations[0].get("name")

        if not station_identifier:
            dispatcher.utter_message(
                text="Kripya station ka naam batayein jiska availability check karna hai."
            )
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE_URL}/stations/availability/{station_identifier}"
                )

                if response.status_code == 200:
                    data = response.json()
                    station = data.get("station", {})

                    status_map = {
                        "high": "Achhi availability",
                        "medium": "Thik availability",
                        "low": "Kam availability - jaldi jayein"
                    }

                    return [
                        SlotSet("station_availability", data),
                        SlotSet("station_name", station.get("name")),
                        SlotSet("available_count", data.get("available_batteries", 0)),
                        SlotSet("availability_status", status_map.get(data.get("status"), data.get("status"))),
                        SlotSet("availability_message", data.get("status_message_hi", data.get("status_message")))
                    ]
                elif response.status_code == 404:
                    dispatcher.utter_message(
                        text=f"'{station_identifier}' naam ka station nahi mila. Kripya sahi naam batayein."
                    )
                    return []
                else:
                    dispatcher.utter_message(
                        text="Availability check karne mein problem hui."
                    )
                    return []

        except Exception as e:
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []