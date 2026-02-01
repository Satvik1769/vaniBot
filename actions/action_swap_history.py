"""Custom actions for swap history and invoice functionality."""
import logging
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Text, Tuple
import httpx
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

logger = logging.getLogger(__name__)

# API Base URL - configure via environment variable in production
API_BASE_URL = "http://localhost:8000/api/v1"

# Time period mapping for normalization
TIME_PERIOD_MAP = {
    # Hindi/Hinglish
    "aaj": "today",
    "abhi": "today",
    "kal": "yesterday",
    "pichhle hafte": "last_week",
    "pichle hafte": "last_week",
    "is hafte": "this_week",
    "pichhle mahine": "last_month",
    "pichle mahine": "last_month",
    "is mahine": "this_month",
    "mahine": "last_month",
    "pichhle saal": "last_year",
    "pichle saal": "last_year",
    "is saal": "this_year",
    "saare": "all",
    "sab": "all",
    "poore": "all",
    # English
    "today": "today",
    "yesterday": "yesterday",
    "last week": "last_week",
    "this week": "this_week",
    "last month": "last_month",
    "this month": "this_month",
    "last year": "last_year",
    "this year": "this_year",
    "all": "all",
}


MONTH_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def parse_date_entity(date_str: str) -> Optional[date]:
    """Parse a date entity string like '31 december' or 'january 15' into a date object."""
    if not date_str:
        return None

    date_str_lower = date_str.lower().strip()
    today = date.today()

    # Try "DD month" pattern (e.g., "31 december")
    match = re.match(r'(\d{1,2})\s*([a-z]+)', date_str_lower)
    if match:
        day = int(match.group(1))
        month_str = match.group(2)
        if month_str in MONTH_MAP:
            month = MONTH_MAP[month_str]
            year = today.year
            # If the date is in the future, use previous year
            try:
                result = date(year, month, day)
                if result > today:
                    result = date(year - 1, month, day)
                return result
            except ValueError:
                return None

    # Try "month DD" pattern (e.g., "december 31")
    match = re.match(r'([a-z]+)\s*(\d{1,2})', date_str_lower)
    if match:
        month_str = match.group(1)
        day = int(match.group(2))
        if month_str in MONTH_MAP:
            month = MONTH_MAP[month_str]
            year = today.year
            try:
                result = date(year, month, day)
                if result > today:
                    result = date(year - 1, month, day)
                return result
            except ValueError:
                return None

    # Try just month name (e.g., "december") - return first day of that month
    if date_str_lower in MONTH_MAP:
        month = MONTH_MAP[date_str_lower]
        year = today.year
        if month > today.month:
            year -= 1
        return date(year, month, 1)

    return None


def parse_time_period(time_period: str) -> Tuple[str, Optional[date], Optional[date]]:
    """Parse time period string and return normalized period with optional custom dates."""
    if not time_period:
        return "all", None, None

    time_period_lower = time_period.lower().strip()

    # Check direct mapping first
    if time_period_lower in TIME_PERIOD_MAP:
        return TIME_PERIOD_MAP[time_period_lower], None, None

    # Handle "pichle N din" or "last N days" patterns
    match = re.search(r'(?:pichle|last)\s*(\d+)\s*(?:din|days?)', time_period_lower)
    if match:
        days = int(match.group(1))
        return str(days), None, None  # Service handles numeric time_period as days

    # Handle "N din" pattern
    match = re.search(r'^(\d+)\s*(?:din|days?)$', time_period_lower)
    if match:
        days = int(match.group(1))
        return str(days), None, None

    # Handle "pichle N hafte" or "last N weeks"
    match = re.search(r'(?:pichle|last)\s*(\d+)\s*(?:hafte|weeks?)', time_period_lower)
    if match:
        weeks = int(match.group(1))
        return str(weeks * 7), None, None

    # If still not matched, return as-is (service will handle or default)
    return time_period_lower, None, None


class ActionFetchSwapHistory(Action):
    """Fetch swap history for the current driver."""

    def name(self) -> Text:
        return "action_fetch_swap_history"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        phone_number = tracker.get_slot("driver_phone")
        raw_time_period = tracker.get_slot("time_period") or "all"
        custom_start = tracker.get_slot("custom_start_date")
        custom_end = tracker.get_slot("custom_end_date")

        # Parse and normalize the time period
        time_period, start_date, end_date = parse_time_period(raw_time_period)

        # Parse custom date entities if available
        if custom_start:
            parsed_start = parse_date_entity(custom_start)
            if parsed_start:
                start_date = parsed_start
                end_date = parsed_start  # Single day query
                time_period = "custom"
                logger.info(f"Parsed date entity '{custom_start}' -> {parsed_start}")

        if custom_end:
            parsed_end = parse_date_entity(custom_end)
            if parsed_end:
                end_date = parsed_end
                time_period = "custom"

        logger.info(f"Fetching swaps for {phone_number}, period={time_period}, start={start_date}, end={end_date}")

        if not phone_number:
            dispatcher.utter_message(
                text="Maaf kijiye, aapka phone number nahi mila. Kripya dubara call karein."
            )
            return []

        try:
            params = {"time_period": time_period, "limit": 10}
            if start_date:
                params["start_date"] = str(start_date)
            if end_date:
                params["end_date"] = str(end_date)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE_URL}/swaps/history/{phone_number}",
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()
                    swaps = data.get("swaps", [])

                    # Format swap list for display
                    swap_list_text = ""
                    for i, swap in enumerate(swaps[:5], 1):
                        swap_time = swap.get("swap_time") or ""
                        time_str = str(swap_time)[:16].replace("T", " ") if swap_time else "Unknown time"
                        station = swap.get("station_name") or "Unknown"
                        amount = swap.get("charge_amount") or 0
                        # Convert to float for comparison (handles Decimal/string)
                        try:
                            amount_float = float(amount)
                        except (ValueError, TypeError):
                            amount_float = 0

                        if amount_float > 0:
                            swap_list_text += f"{i}. {time_str} - {station} - ₹{amount}\n"
                        else:
                            swap_list_text += f"{i}. {time_str} - {station} - Free (subscription)\n"

                    return [
                        SlotSet("swap_history", swaps),
                        SlotSet("swap_history_message", data.get("message_hi", data.get("message"))),
                        SlotSet("swap_list", swap_list_text or "Koi swap nahi mila.")
                    ]
                else:
                    dispatcher.utter_message(
                        text="Swap history fetch karne mein problem hui. Thodi der baad try karein."
                    )
                    return []

        except Exception as e:
            logger.exception(f"Error fetching swap history: {e}")
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []


class ActionFetchSwapHistoryWithSMS(Action):
    """Fetch swap history and send it via SMS."""

    def name(self) -> Text:
        return "action_fetch_swap_history_sms"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        phone_number = tracker.get_slot("driver_phone")
        raw_time_period = tracker.get_slot("time_period") or "all"

        # Parse and normalize the time period
        time_period, start_date, end_date = parse_time_period(raw_time_period)

        if not phone_number:
            dispatcher.utter_message(
                text="Maaf kijiye, aapka phone number nahi mila."
            )
            return []

        try:
            params = {"time_period": time_period}
            if start_date:
                params["start_date"] = str(start_date)
            if end_date:
                params["end_date"] = str(end_date)

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{API_BASE_URL}/swaps/history/send-sms/{phone_number}",
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()
                    sms_sent = data.get("sms_sent", False)

                    if sms_sent:
                        return [
                            SlotSet("swap_history", data.get("swap_history", {}).get("swaps", [])),
                            SlotSet("sms_sent", True),
                            SlotSet("swap_history_message",
                                    f"Aapki swap history {phone_number} pe SMS kar di hai.")
                        ]
                    else:
                        return [
                            SlotSet("swap_history", data.get("swap_history", {}).get("swaps", [])),
                            SlotSet("sms_sent", False),
                            SlotSet("swap_history_message",
                                    data.get("swap_history", {}).get("message_hi", "Swap history mil gayi."))
                        ]
                else:
                    dispatcher.utter_message(
                        text="Swap history fetch karne mein problem hui."
                    )
                    return []

        except Exception as e:
            logger.exception(f"Error fetching swap history with SMS: {e}")
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []


class ActionExplainInvoice(Action):
    """Explain invoice details to the driver."""

    def name(self) -> Text:
        return "action_explain_invoice"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        phone_number = tracker.get_slot("driver_phone")
        invoice_id = tracker.get_slot("invoice_id")

        if not phone_number:
            dispatcher.utter_message(
                text="Maaf kijiye, aapka phone number nahi mila."
            )
            return []

        try:
            async with httpx.AsyncClient() as client:
                # Use the endpoint that includes penalty information
                response = await client.get(
                    f"{API_BASE_URL}/swaps/invoice-with-penalty/{phone_number}",
                    params={"invoice_number": invoice_id} if invoice_id else {}
                )

                if response.status_code == 200:
                    data = response.json()
                    invoice = data.get("invoice", {})
                    has_penalty = data.get("has_penalty", False)

                    # Format breakdown
                    breakdown_text = ""
                    for item in data.get("breakdown", []):
                        breakdown_text += f"- {item.get('item_hi', item.get('item'))}: ₹{item.get('amount')}\n"

                    # Add penalty warning if applicable
                    explanation = data.get("explanation_hi", data.get("explanation", ""))
                    if has_penalty:
                        penalty = data.get("penalty", {})
                        penalty_msg = (
                            f"\n\n⚠️ PENALTY ALERT: Rs.{penalty.get('penalty_amount', 0):.0f} ki penalty hai "
                            f"kyunki battery {penalty.get('days_overdue', 0)} din se return nahi hui. "
                            f"Rs.80 per day lagta hai subscription end ke 4 din baad."
                        )
                        explanation += penalty_msg

                    return [
                        SlotSet("invoice_details", data),
                        SlotSet("invoice_explanation", explanation),
                        SlotSet("invoice_breakdown", breakdown_text),
                        SlotSet("has_penalty", has_penalty),
                        SlotSet("penalty_amount", data.get("penalty", {}).get("penalty_amount", 0) if has_penalty else 0)
                    ]
                elif response.status_code == 404:
                    dispatcher.utter_message(
                        text="Koi invoice nahi mila. Aapne recently koi charged swap kiya hai?"
                    )
                    return []
                else:
                    dispatcher.utter_message(
                        text="Invoice details fetch karne mein problem hui."
                    )
                    return []

        except Exception as e:
            logger.exception(f"Error explaining invoice: {e}")
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []


class ActionCheckPenalty(Action):
    """Check if there's a penalty for unreturned battery."""

    def name(self) -> Text:
        return "action_check_penalty"

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
                    f"{API_BASE_URL}/swaps/penalty/{phone_number}"
                )

                if response.status_code == 200:
                    data = response.json()
                    has_penalty = data.get("has_penalty", False)

                    return [
                        SlotSet("has_penalty", has_penalty),
                        SlotSet("penalty_amount", data.get("penalty_amount", 0)),
                        SlotSet("days_overdue", data.get("days_overdue", 0)),
                        SlotSet("penalty_message", data.get("message_hi", data.get("message")))
                    ]
                else:
                    return [
                        SlotSet("has_penalty", False),
                        SlotSet("penalty_amount", 0)
                    ]

        except Exception as e:
            logger.exception(f"Error checking penalty: {e}")
            dispatcher.utter_message(
                text="Technical issue hui hai."
            )
            return []