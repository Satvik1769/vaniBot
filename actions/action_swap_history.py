"""Custom actions for swap history and invoice functionality."""
from typing import Any, Dict, List, Text
import httpx
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

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
        time_period = tracker.get_slot("time_period") or "today"

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
                        time_str = swap.get("swap_time", "")[:16].replace("T", " ")
                        station = swap.get("station_name", "Unknown")
                        amount = swap.get("charge_amount", 0)
                        if amount > 0:
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
                params = {"phone_number": phone_number}
                if invoice_id:
                    params["invoice_number"] = invoice_id

                response = await client.post(
                    f"{API_BASE_URL}/swaps/invoice",
                    json=params
                )

                if response.status_code == 200:
                    data = response.json()
                    invoice = data.get("invoice", {})

                    # Format breakdown
                    breakdown_text = ""
                    for item in data.get("breakdown", []):
                        breakdown_text += f"- {item.get('item_hi', item.get('item'))}: ₹{item.get('amount')}\n"

                    return [
                        SlotSet("invoice_details", data),
                        SlotSet("invoice_explanation", data.get("explanation_hi", data.get("explanation"))),
                        SlotSet("invoice_breakdown", breakdown_text)
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
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []