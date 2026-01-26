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
    """Find nearest DSK locations."""

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

        try:
            async with httpx.AsyncClient() as client:
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
                    services_text = ", ".join(nearest.get("services", []))

                    return [
                        SlotSet("nearest_dsk", nearest),
                        SlotSet("dsk_name", nearest.get("name")),
                        SlotSet("dsk_address", nearest.get("address")),
                        SlotSet("dsk_phone", nearest.get("phone")),
                        SlotSet("dsk_hours", nearest.get("operating_hours")),
                        SlotSet("dsk_services", services_text)
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