"""Custom actions for DSK finder and leave management."""
from typing import Any, Dict, List, Text
from datetime import datetime, timedelta
import httpx
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

API_BASE_URL = "http://localhost:8000/api/v1"


class ActionFindNearestDSK(Action):
    """Find nearest DSK locations using phone-based geolocation."""

    def name(self) -> Text:
        return "action_find_nearest_dsk"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        location = tracker.get_slot("user_location")
        service_type = tracker.get_slot("service_type")
        phone_number = tracker.get_slot("driver_phone")

        try:
            async with httpx.AsyncClient() as client:
                # Try phone-based geolocation first
                if phone_number:
                    response = await client.get(
                        f"{API_BASE_URL}/stations/dsk/nearest-by-phone/{phone_number}",
                        params={"limit": 3}
                    )
                else:
                    params = {"limit": 3}
                    if location:
                        params["city"] = location
                    if service_type:
                        params["service_type"] = service_type

                    response = await client.get(
                        f"{API_BASE_URL}/dsk/nearest",
                        params=params
                    )

                if response.status_code == 200:
                    data = response.json()
                    dsk_locations = data.get("dsk_locations", [])

                    if not dsk_locations:
                        dispatcher.utter_message(
                            text="Is area mein koi DSK nahi mila. Kripya koi aur location try karein."
                        )
                        return []

                    nearest = dsk_locations[0]
                    services_text = ", ".join(nearest.get("services", [])) if nearest.get("services") else "All services"

                    # Include Google Maps URL
                    maps_url = nearest.get("google_map_url", "")
                    if not maps_url and nearest.get("latitude") and nearest.get("longitude"):
                        maps_url = f"https://www.google.com/maps/dir/?api=1&destination={nearest['latitude']},{nearest['longitude']}"

                    return [
                        SlotSet("nearest_dsk", nearest),
                        SlotSet("dsk_name", nearest.get("name")),
                        SlotSet("dsk_address", nearest.get("address")),
                        SlotSet("dsk_phone", nearest.get("phone") or nearest.get("contact_phone")),
                        SlotSet("dsk_hours", nearest.get("operating_hours")),
                        SlotSet("dsk_services", services_text),
                        SlotSet("dsk_maps_url", maps_url)
                    ]
                else:
                    dispatcher.utter_message(
                        text="DSK dhundhne mein problem hui."
                    )
                    return []

        except Exception as e:
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []


class ActionGetActivationInfo(Action):
    """Get activation information and requirements."""

    def name(self) -> Text:
        return "action_get_activation_info"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        location = tracker.get_slot("user_location")

        try:
            async with httpx.AsyncClient() as client:
                params = {}
                if location:
                    params["city"] = location

                response = await client.get(
                    f"{API_BASE_URL}/dsk/activation",
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()

                    # Format documents list
                    docs_text = "\n".join([f"• {doc}" for doc in data.get("required_documents_hi", [])])

                    # Format process steps
                    steps_text = "\n".join([f"{i}. {step}" for i, step in enumerate(data.get("process_steps_hi", []), 1)])

                    nearest_dsk = data.get("nearest_dsk", {})

                    return [
                        SlotSet("activation_info", data),
                        SlotSet("required_docs", docs_text),
                        SlotSet("process_steps", steps_text),
                        SlotSet("estimated_time", data.get("estimated_time_hi")),
                        SlotSet("dsk_name", nearest_dsk.get("name") if nearest_dsk else None)
                    ]
                else:
                    dispatcher.utter_message(
                        text="Activation information fetch karne mein problem hui."
                    )
                    return []

        except Exception as e:
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []


class ActionApplyLeave(Action):
    """Apply for leave."""

    def name(self) -> Text:
        return "action_apply_leave"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        phone_number = tracker.get_slot("driver_phone")
        start_date = tracker.get_slot("leave_start_date")
        end_date = tracker.get_slot("leave_end_date")
        reason = tracker.get_slot("leave_reason")

        if not phone_number:
            dispatcher.utter_message(
                text="Maaf kijiye, aapka phone number nahi mila."
            )
            return []

        # Parse dates - handle common formats
        def parse_date(date_str):
            if not date_str:
                return None

            date_str = date_str.lower().strip()
            today = datetime.now().date()

            # Handle relative dates
            if date_str in ["kal", "tomorrow"]:
                return today + timedelta(days=1)
            elif date_str in ["aaj", "today"]:
                return today
            elif date_str in ["parson", "day after tomorrow"]:
                return today + timedelta(days=2)

            # Try parsing various formats
            for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %B", "%d %b"]:
                try:
                    parsed = datetime.strptime(date_str, fmt)
                    if parsed.year == 1900:  # No year in format
                        parsed = parsed.replace(year=today.year)
                    return parsed.date()
                except ValueError:
                    continue

            return None

        parsed_start = parse_date(start_date)
        parsed_end = parse_date(end_date) or parsed_start

        if not parsed_start:
            dispatcher.utter_message(
                text="Start date samajh nahi aayi. Kripya date dobara batayein (e.g., kal, 28 January)"
            )
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{API_BASE_URL}/dsk/leave",
                    json={
                        "phone_number": phone_number,
                        "start_date": str(parsed_start),
                        "end_date": str(parsed_end),
                        "reason": reason if reason and reason.lower() != "skip" else None
                    }
                )

                if response.status_code == 200:
                    data = response.json()

                    return [
                        SlotSet("leave_start_date", str(data.get("start_date"))),
                        SlotSet("leave_end_date", str(data.get("end_date"))),
                        SlotSet("leave_days", data.get("days"))
                    ]
                elif response.status_code == 404:
                    dispatcher.utter_message(
                        text="Aapka account nahi mila. Kripya pehle registration karein."
                    )
                    return []
                else:
                    dispatcher.utter_message(
                        text="Leave apply karne mein problem hui."
                    )
                    return []

        except Exception as e:
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []


class ActionCheckLeaveStatus(Action):
    """Check leave status for the driver."""

    def name(self) -> Text:
        return "action_check_leave_status"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        phone_number = tracker.get_slot("driver_phone")

        if not phone_number:
            dispatcher.utter_message(
                text="Maaf kijiye, aapka phone number nahi mila."
            )
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE_URL}/dsk/leave/{phone_number}"
                )

                if response.status_code == 200:
                    data = response.json()

                    # Format leave details
                    leave_details = ""
                    for leave in data.get("pending_leaves", []):
                        leave_details += f"• {leave.get('start_date')} to {leave.get('end_date')} - Pending\n"
                    for leave in data.get("approved_leaves", []):
                        leave_details += f"• {leave.get('start_date')} to {leave.get('end_date')} - Approved\n"

                    return [
                        SlotSet("leave_status", data),
                        SlotSet("leave_status_message", data.get("message_hi", data.get("message"))),
                        SlotSet("pending_count", data.get("total_pending", 0)),
                        SlotSet("approved_count", data.get("total_approved", 0)),
                        SlotSet("leave_details", leave_details or "Koi leave nahi mili.")
                    ]
                else:
                    dispatcher.utter_message(
                        text="Leave status check karne mein problem hui."
                    )
                    return []

        except Exception as e:
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []


class ActionCheckLeaveBalance(Action):
    """Check remaining leave balance for the month (4 leaves per month)."""

    def name(self) -> Text:
        return "action_check_leave_balance"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        phone_number = tracker.get_slot("driver_phone")

        if not phone_number:
            dispatcher.utter_message(
                text="Maaf kijiye, aapka phone number nahi mila."
            )
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE_URL}/dsk/leave-balance/{phone_number}"
                )

                if response.status_code == 200:
                    data = response.json()

                    return [
                        SlotSet("total_leaves", data.get("total_leaves", 4)),
                        SlotSet("used_leaves", data.get("used_leaves", 0)),
                        SlotSet("remaining_leaves", data.get("remaining_leaves", 4)),
                        SlotSet("leave_balance_message", data.get("message_hi", data.get("message")))
                    ]
                elif response.status_code == 404:
                    dispatcher.utter_message(
                        text="Aapka account nahi mila. Kripya pehle registration karein."
                    )
                    return []
                else:
                    dispatcher.utter_message(
                        text="Leave balance check karne mein problem hui."
                    )
                    return []

        except Exception as e:
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []


class ActionApplyLeaveWithBalance(Action):
    """Apply for leave and deduct from balance."""

    def name(self) -> Text:
        return "action_apply_leave_with_balance"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        phone_number = tracker.get_slot("driver_phone")
        start_date = tracker.get_slot("leave_start_date")
        end_date = tracker.get_slot("leave_end_date")
        reason = tracker.get_slot("leave_reason")

        if not phone_number:
            dispatcher.utter_message(
                text="Maaf kijiye, aapka phone number nahi mila."
            )
            return []

        # Parse dates - handle common formats
        def parse_date(date_str):
            if not date_str:
                return None

            date_str = date_str.lower().strip()
            today = datetime.now().date()

            # Handle relative dates
            if date_str in ["kal", "tomorrow"]:
                return today + timedelta(days=1)
            elif date_str in ["aaj", "today"]:
                return today
            elif date_str in ["parson", "day after tomorrow"]:
                return today + timedelta(days=2)

            # Try parsing various formats
            for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %B", "%d %b"]:
                try:
                    parsed = datetime.strptime(date_str, fmt)
                    if parsed.year == 1900:  # No year in format
                        parsed = parsed.replace(year=today.year)
                    return parsed.date()
                except ValueError:
                    continue

            return None

        parsed_start = parse_date(start_date)
        parsed_end = parse_date(end_date) or parsed_start

        if not parsed_start:
            dispatcher.utter_message(
                text="Start date samajh nahi aayi. Kripya date dobara batayein (e.g., kal, 28 January)"
            )
            return []

        try:
            async with httpx.AsyncClient() as client:
                # Use the endpoint that checks and deducts balance
                response = await client.post(
                    f"{API_BASE_URL}/dsk/leave/with-balance",
                    json={
                        "phone_number": phone_number,
                        "start_date": str(parsed_start),
                        "end_date": str(parsed_end),
                        "reason": reason if reason and reason.lower() != "skip" else None
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    leave_balance = data.get("leave_balance", {})

                    return [
                        SlotSet("leave_start_date", str(data.get("start_date"))),
                        SlotSet("leave_end_date", str(data.get("end_date"))),
                        SlotSet("leave_days", data.get("days")),
                        SlotSet("remaining_leaves", leave_balance.get("remaining_after", 0)),
                        SlotSet("leave_applied_message",
                                f"Leave apply ho gayi. Aapke paas ab {leave_balance.get('remaining_after', 0)} leaves bachi hain.")
                    ]
                elif response.status_code == 400:
                    error_data = response.json().get("detail", {})
                    if isinstance(error_data, dict):
                        msg = error_data.get("message_hi", error_data.get("message", "Leave apply nahi ho payi."))
                        remaining = error_data.get("remaining_leaves", 0)
                        dispatcher.utter_message(
                            text=f"{msg} Aapke paas sirf {remaining} leaves bachi hain."
                        )
                    else:
                        dispatcher.utter_message(text=str(error_data))
                    return []
                elif response.status_code == 404:
                    dispatcher.utter_message(
                        text="Aapka account nahi mila. Kripya pehle registration karein."
                    )
                    return []
                else:
                    dispatcher.utter_message(
                        text="Leave apply karne mein problem hui."
                    )
                    return []

        except Exception as e:
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []