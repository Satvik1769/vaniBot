"""Custom actions for swap history and invoice functionality."""
import logging
from decimal import Decimal
from typing import Any, Dict, List, Text
import httpx
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

logger = logging.getLogger(__name__)

# API Base URL - configure via environment variable in production
API_BASE_URL = "http://localhost:8000/api/v1"


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
        time_period = tracker.get_slot("time_period") or "all"

        if not phone_number:
            dispatcher.utter_message(
                text="Maaf kijiye, aapka phone number nahi mila. Kripya dubara call karein."
            )
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE_URL}/swaps/history/{phone_number}",
                    params={"time_period": time_period, "limit": 10}
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
        time_period = tracker.get_slot("time_period") or "all"

        if not phone_number:
            dispatcher.utter_message(
                text="Maaf kijiye, aapka phone number nahi mila."
            )
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{API_BASE_URL}/swaps/history/send-sms/{phone_number}",
                    params={"time_period": time_period}
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