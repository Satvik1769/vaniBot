"""Custom actions for subscription management."""
from typing import Any, Dict, List, Text
import httpx
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

API_BASE_URL = "http://localhost:8000/api/v1"


class ActionCheckSubscription(Action):
    """Check subscription status for the driver."""

    def name(self) -> Text:
        return "action_check_subscription"

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
                    f"{API_BASE_URL}/subscriptions/status/{phone_number}"
                )

                if response.status_code == 200:
                    data = response.json()
                    subscription = data.get("subscription")

                    if subscription:
                        swaps_info = ""
                        swaps_remaining = subscription.get("swaps_remaining", -1)
                        if swaps_remaining == -1:
                            swaps_info = "Unlimited swaps"
                        else:
                            swaps_info = f"{swaps_remaining} swaps bache"

                        return [
                            SlotSet("subscription_status", subscription),
                            SlotSet("subscription_message", data.get("message_hi", data.get("message"))),
                            SlotSet("plan_name", subscription.get("plan_name_hi") or subscription.get("plan_name")),
                            SlotSet("plan_status", subscription.get("status")),
                            SlotSet("end_date", str(subscription.get("end_date"))),
                            SlotSet("days_remaining", subscription.get("days_remaining")),
                            SlotSet("swaps_info", swaps_info),
                            SlotSet("subscription_expiring_soon", subscription.get("is_expiring_soon", False))
                        ]
                    else:
                        return [
                            SlotSet("subscription_status", None),
                            SlotSet("subscription_message", data.get("message_hi", data.get("message"))),
                            SlotSet("subscription_expiring_soon", False)
                        ]
                elif response.status_code == 404:
                    dispatcher.utter_message(
                        text="Aapka account nahi mila. Kripya pehle registration karein."
                    )
                    return []
                else:
                    dispatcher.utter_message(
                        text="Subscription status check karne mein problem hui."
                    )
                    return []

        except Exception as e:
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []


class ActionShowPricing(Action):
    """Show all subscription plans and pricing."""

    def name(self) -> Text:
        return "action_show_pricing"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{API_BASE_URL}/subscriptions/plans")

                if response.status_code == 200:
                    data = response.json()
                    plans = data.get("plans", [])

                    # Format pricing list
                    pricing_list = ""
                    for plan in plans:
                        name = plan.get("name_hi") or plan.get("name")
                        price = plan.get("price")
                        swaps = plan.get("swaps_included")
                        validity = plan.get("validity_days")

                        if swaps == -1:
                            swaps_text = "Unlimited swaps"
                        else:
                            swaps_text = f"{swaps} swaps"

                        pricing_list += f"• {name} - ₹{price}/{validity} din - {swaps_text}\n"

                    return [
                        SlotSet("pricing_info", data),
                        SlotSet("pricing_list", pricing_list)
                    ]
                else:
                    dispatcher.utter_message(
                        text="Pricing information fetch karne mein problem hui."
                    )
                    return []

        except Exception as e:
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []


class ActionProcessRenewal(Action):
    """Process subscription renewal."""

    def name(self) -> Text:
        return "action_process_renewal"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        phone_number = tracker.get_slot("driver_phone")
        selected_plan = tracker.get_slot("selected_plan")

        if not phone_number:
            dispatcher.utter_message(
                text="Maaf kijiye, aapka phone number nahi mila."
            )
            return []

        if not selected_plan:
            dispatcher.utter_message(
                text="Kripya pehle plan select karein."
            )
            return []

        # Normalize plan code
        plan_code = selected_plan.upper()
        if plan_code not in ["DAILY", "WEEKLY", "MONTHLY", "YEARLY"]:
            # Try to match partial names
            plan_map = {
                "DAILY": ["DAILY", "ROZANA", "DAY"],
                "WEEKLY": ["WEEKLY", "HAFTA", "WEEK"],
                "MONTHLY": ["MONTHLY", "MAHINA", "MONTH"],
                "YEARLY": ["YEARLY", "SAAL", "YEAR", "ANNUAL"]
            }
            for code, variants in plan_map.items():
                if any(v in plan_code for v in variants):
                    plan_code = code
                    break

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{API_BASE_URL}/subscriptions/renew",
                    json={
                        "phone_number": phone_number,
                        "plan_code": plan_code,
                        "auto_renew": False
                    }
                )

                if response.status_code == 200:
                    data = response.json()

                    return [
                        SlotSet("plan_name", data.get("plan_name")),
                        SlotSet("plan_price", data.get("price")),
                        SlotSet("tax_amount", data.get("tax")),
                        SlotSet("total_amount", data.get("total")),
                        SlotSet("validity_days", data.get("validity_days")),
                        SlotSet("start_date", str(data.get("start_date"))),
                        SlotSet("end_date", str(data.get("end_date")))
                    ]
                elif response.status_code == 404:
                    dispatcher.utter_message(
                        text="Aapka account nahi mila. Kripya pehle registration karein."
                    )
                    return []
                elif response.status_code == 400:
                    dispatcher.utter_message(
                        text="Invalid plan. Kripya Daily, Weekly, Monthly ya Yearly mein se choose karein."
                    )
                    return []
                else:
                    dispatcher.utter_message(
                        text="Subscription renew karne mein problem hui."
                    )
                    return []

        except Exception as e:
            dispatcher.utter_message(
                text="Technical issue hui hai. Kripya thodi der baad try karein."
            )
            return []