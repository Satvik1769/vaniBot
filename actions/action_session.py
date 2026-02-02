"""Custom actions for session management and driver identification."""
from typing import Any, Dict, List, Text
import logging
import httpx
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

logger = logging.getLogger(__name__)

API_BASE_URL = "http://54.245.152.155:8000/api/v1"


class ActionSessionStart(Action):
    """Initialize session when call starts."""

    def name(self) -> Text:
        return "action_session_start"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        # Get phone number from metadata (passed from voice orchestrator)
        metadata = tracker.latest_message.get("metadata", {})
        phone_number = metadata.get("phone_number") or metadata.get("caller_id")

        logger.info(f"[SessionStart] Metadata received: {metadata}")
        logger.info(f"[SessionStart] Phone number extracted: {phone_number}")

        events = []

        if phone_number:
            # Clean phone number (remove +91, spaces, etc.)
            phone_number = phone_number.replace("+91", "").replace(" ", "").strip()
            if len(phone_number) > 10:
                phone_number = phone_number[-10:]

            logger.info(f"[SessionStart] Setting driver_phone slot to: {phone_number}")
            events.append(SlotSet("driver_phone", phone_number))

            # Try to identify driver
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{API_BASE_URL}/drivers/identify",
                        json={"phone_number": phone_number}
                    )

                    if response.status_code == 200:
                        data = response.json()
                        driver = data.get("driver", {})

                        events.extend([
                            SlotSet("driver_id", str(driver.get("id"))),
                            SlotSet("driver_name", driver.get("name")),
                            SlotSet("preferred_language", driver.get("preferred_language", "hi-en"))
                        ])

                        if data.get("is_new"):
                            events.append(SlotSet("is_new_driver", True))
            except Exception:
                pass  # Continue without driver info

        return events


class ActionIdentifyDriver(Action):
    """Identify driver from phone number."""

    def name(self) -> Text:
        return "action_identify_driver"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        phone_number = tracker.get_slot("driver_phone")

        if not phone_number:
            return []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{API_BASE_URL}/drivers/identify",
                    json={"phone_number": phone_number}
                )

                if response.status_code == 200:
                    data = response.json()
                    driver = data.get("driver", {})

                    return [
                        SlotSet("driver_id", str(driver.get("id"))),
                        SlotSet("driver_name", driver.get("name")),
                        SlotSet("preferred_language", driver.get("preferred_language", "hi-en")),
                        SlotSet("is_new_driver", data.get("is_new", False))
                    ]
        except Exception:
            pass

        return []


class ActionDetectLanguage(Action):
    """Detect language from user's message and update preference."""

    def name(self) -> Text:
        return "action_detect_language"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        latest_message = tracker.latest_message.get("text", "")

        # Simple language detection based on script
        has_devanagari = any('\u0900' <= c <= '\u097F' for c in latest_message)
        has_english = any('a' <= c.lower() <= 'z' for c in latest_message)

        if has_devanagari and not has_english:
            detected = "hi"
        elif has_english and not has_devanagari:
            # Check for Hindi words in Roman script
            hindi_words = ["hai", "kya", "kahan", "mera", "meri", "batao", "dikhao",
                         "chahiye", "karo", "karein", "nahi", "haan", "theek"]
            words = latest_message.lower().split()
            if any(word in hindi_words for word in words):
                detected = "hi-en"  # Hinglish
            else:
                detected = "en"
        else:
            detected = "hi-en"  # Mixed - default to Hinglish

        # Update driver preference if different
        phone_number = tracker.get_slot("driver_phone")
        current_pref = tracker.get_slot("preferred_language")

        if phone_number and detected != current_pref:
            try:
                async with httpx.AsyncClient() as client:
                    await client.put(
                        f"{API_BASE_URL}/drivers/{phone_number}/language",
                        params={"language": detected}
                    )
            except Exception:
                pass

        return [SlotSet("preferred_language", detected)]


class ActionSessionEnd(Action):
    """End session and log conversation."""

    def name(self) -> Text:
        return "action_session_end"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        session_id = tracker.sender_id
        phone_number = tracker.get_slot("driver_phone")

        # Collect conversation summary
        intents = []
        for event in tracker.events:
            if event.get("event") == "user":
                intent = event.get("parse_data", {}).get("intent", {}).get("name")
                if intent and intent not in intents:
                    intents.append(intent)

        # Log to API (fire and forget)
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{API_BASE_URL}/voice/session/end",
                    params={
                        "session_id": session_id,
                        "resolution_status": "resolved"
                    }
                )
        except Exception:
            pass

        return []