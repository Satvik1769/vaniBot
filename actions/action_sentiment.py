"""Custom actions for sentiment analysis and escalation logic."""
from typing import Any, Dict, List, Text
import os
import json
import google.generativeai as genai
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

# Configure Gemini
GEMINI_API_KEY = os.getenv("LLM_PROVIDER_API_KEY") or os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Confidence thresholds
CONFIDENCE_HIGH = 0.85
CONFIDENCE_MEDIUM = 0.60
CONFIDENCE_LOW = 0.45
CONFIDENCE_CRITICAL = 0.30

# Sentiment thresholds
SENTIMENT_POSITIVE = 0.3
SENTIMENT_NEUTRAL = -0.2
SENTIMENT_NEGATIVE = -0.5
SENTIMENT_CRITICAL = -0.7


class ActionAnalyzeSentiment(Action):
    """Analyze sentiment of user's message using Gemini."""

    def name(self) -> Text:
        return "action_analyze_sentiment"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        latest_message = tracker.latest_message.get("text", "")

        if not latest_message or not GEMINI_API_KEY:
            return []

        try:
            model = genai.GenerativeModel("gemini-pro")

            prompt = f"""Analyze the sentiment of this Hindi/English customer support utterance.

Consider these indicators:
- Frustration markers: kyun, kab tak, phir se, kitni baar, why again
- Urgency markers: jaldi, abhi, turant, urgent, now
- Politeness markers: please, kripya, dhanyavaad, thanks
- Negative markers: bekaar, ghatiya, worst, problem, issue
- Positive markers: achha, badiya, great, thanks, helpful

Utterance: "{latest_message}"

Return ONLY a JSON object (no markdown, no explanation):
{{"score": <float from -1.0 to 1.0>, "emotion": "<primary emotion>", "escalate": <true/false>, "confidence": <float 0-1>}}

Emotions: happy, satisfied, neutral, confused, frustrated, angry, disappointed"""

            response = model.generate_content(prompt)
            result_text = response.text.strip()

            # Clean up response (remove markdown if present)
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            result_text = result_text.strip()

            result = json.loads(result_text)

            sentiment_score = float(result.get("score", 0))
            emotion = result.get("emotion", "neutral")
            should_escalate = result.get("escalate", False)

            # Update low confidence counter
            current_confidence = tracker.get_slot("current_confidence") or 1.0
            low_conf_count = tracker.get_slot("low_confidence_count") or 0

            if current_confidence < CONFIDENCE_MEDIUM:
                low_conf_count += 1
            else:
                low_conf_count = max(0, low_conf_count - 1)

            # Check escalation conditions
            escalation_reason = None

            # Condition 1: Sentiment below critical threshold
            if sentiment_score < SENTIMENT_CRITICAL:
                should_escalate = True
                escalation_reason = "critical_sentiment"

            # Condition 2: Sharp sentiment drop
            prev_sentiment = tracker.get_slot("current_sentiment") or 0
            if prev_sentiment - sentiment_score > 0.4:
                should_escalate = True
                escalation_reason = "sentiment_drop"

            # Condition 3: Multiple low confidence turns
            if low_conf_count >= 3:
                should_escalate = True
                escalation_reason = "low_confidence_streak"

            return [
                SlotSet("current_sentiment", sentiment_score),
                SlotSet("detected_emotion", emotion),
                SlotSet("low_confidence_count", low_conf_count),
                SlotSet("should_escalate", should_escalate),
                SlotSet("escalation_reason", escalation_reason)
            ]

        except Exception as e:
            # On error, return neutral sentiment
            return [
                SlotSet("current_sentiment", 0.0),
                SlotSet("detected_emotion", "neutral")
            ]


class ActionCheckEscalation(Action):
    """Check if conversation should be escalated to human agent."""

    def name(self) -> Text:
        return "action_check_escalation"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        # Get current metrics
        sentiment = tracker.get_slot("current_sentiment") or 0
        confidence = tracker.get_slot("current_confidence") or 1.0
        low_conf_count = tracker.get_slot("low_confidence_count") or 0
        already_escalating = tracker.get_slot("should_escalate") or False

        # Check for explicit handoff request
        latest_intent = tracker.latest_message.get("intent", {}).get("name", "")
        if latest_intent == "request_human":
            return [
                SlotSet("should_escalate", True),
                SlotSet("escalation_reason", "explicit_request")
            ]

        # Check for loop detection (same intent repeated)
        recent_intents = []
        for event in reversed(tracker.events):
            if event.get("event") == "user":
                intent = event.get("parse_data", {}).get("intent", {}).get("name")
                if intent:
                    recent_intents.append(intent)
                    if len(recent_intents) >= 4:
                        break

        if len(recent_intents) >= 3 and len(set(recent_intents[:3])) == 1:
            return [
                SlotSet("should_escalate", True),
                SlotSet("escalation_reason", "loop_detected")
            ]

        # Check confidence threshold
        if confidence < CONFIDENCE_CRITICAL:
            return [
                SlotSet("should_escalate", True),
                SlotSet("escalation_reason", "critical_confidence")
            ]

        # Check sentiment threshold
        if sentiment < SENTIMENT_CRITICAL:
            return [
                SlotSet("should_escalate", True),
                SlotSet("escalation_reason", "critical_sentiment")
            ]

        # Check combined score
        if confidence < CONFIDENCE_LOW and sentiment < SENTIMENT_NEGATIVE:
            return [
                SlotSet("should_escalate", True),
                SlotSet("escalation_reason", "combined_low_scores")
            ]

        return [SlotSet("should_escalate", already_escalating)]


class ActionTriggerHandoff(Action):
    """Trigger handoff to human agent with summary."""

    def name(self) -> Text:
        return "action_trigger_handoff"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        escalation_reason = tracker.get_slot("escalation_reason")
        driver_name = tracker.get_slot("driver_name")

        # Prepare handoff message
        if escalation_reason == "explicit_request":
            msg = f"Theek hai{', ' + driver_name if driver_name else ''}, main aapko hamare customer support se connect kar rahi hoon. Kripya hold karein."
        elif escalation_reason in ["critical_sentiment", "sentiment_drop"]:
            msg = "Main samajh sakti hoon ki aap pareshan hain. Main aapko hamare expert se connect kar rahi hoon jo aapki behtar madad kar payenge."
        elif escalation_reason in ["low_confidence_streak", "loop_detected"]:
            msg = "Lagta hai main aapki query properly samajh nahi paa rahi. Main aapko hamare agent se connect kar rahi hoon."
        else:
            msg = "Main aapko hamare customer support team se connect kar rahi hoon. Kripya hold karein."

        dispatcher.utter_message(text=msg)

        return [SlotSet("handoff_initiated", True)]


class ActionGenerateHandoffSummary(Action):
    """Generate summary for human agent handoff."""

    def name(self) -> Text:
        return "action_generate_handoff_summary"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        # Collect conversation history
        conversation = []
        for event in tracker.events:
            if event.get("event") == "user":
                conversation.append(f"Customer: {event.get('text', '')}")
            elif event.get("event") == "bot":
                conversation.append(f"Bot: {event.get('text', '')}")

        # Collect intents
        intents = []
        for event in tracker.events:
            if event.get("event") == "user":
                intent = event.get("parse_data", {}).get("intent", {}).get("name")
                if intent and intent not in intents:
                    intents.append(intent)

        # Get slot values
        phone_number = tracker.get_slot("driver_phone") or "Unknown"
        driver_name = tracker.get_slot("driver_name") or "Unknown"
        preferred_language = tracker.get_slot("preferred_language") or "hi-en"
        subscription = tracker.get_slot("subscription_status")
        sentiment = tracker.get_slot("current_sentiment") or 0
        confidence = tracker.get_slot("current_confidence") or 1.0
        emotion = tracker.get_slot("detected_emotion") or "neutral"
        escalation_reason = tracker.get_slot("escalation_reason") or "unknown"

        # Generate summary using Gemini
        summary = "Conversation summary not available"
        if GEMINI_API_KEY and conversation:
            try:
                model = genai.GenerativeModel("gemini-pro")

                prompt = f"""Summarize this customer support conversation in 2-3 sentences.
Focus on: What the customer wanted, what was discussed, why escalation happened.

Conversation:
{chr(10).join(conversation[-20:])}

Write summary in English, be concise."""

                response = model.generate_content(prompt)
                summary = response.text.strip()
            except Exception:
                summary = f"Customer called regarding: {', '.join(intents[:3])}"

        # Format handoff summary
        handoff_summary = {
            "session_id": tracker.sender_id,
            "phone_number": phone_number,
            "driver_name": driver_name,
            "driver_language": preferred_language,
            "plan_name": subscription.get("plan_name") if subscription else None,
            "plan_status": subscription.get("status") if subscription else None,
            "plan_expiry": subscription.get("end_date") if subscription else None,
            "conversation_summary": summary,
            "intents_detected": intents,
            "turns_count": len([e for e in tracker.events if e.get("event") in ["user", "bot"]]),
            "escalation_trigger": escalation_reason,
            "confidence_score": round(confidence, 2),
            "sentiment_score": round(sentiment, 2),
            "detected_emotion": emotion,
            "recommended_actions": _get_recommended_actions(intents, escalation_reason)
        }

        return [SlotSet("handoff_summary", handoff_summary)]


def _get_recommended_actions(intents: List[str], escalation_reason: str) -> List[str]:
    """Generate recommended actions for the agent."""
    actions = []

    # Based on intents
    if "check_swap_history" in intents or "explain_invoice" in intents:
        actions.append("Review customer's recent swap transactions and invoices")
    if "check_subscription" in intents or "renew_subscription" in intents:
        actions.append("Check subscription status and discuss renewal options")
    if "find_nearest_station" in intents:
        actions.append("Help locate nearby swap stations")
    if "apply_leave" in intents:
        actions.append("Assist with leave application")

    # Based on escalation reason
    if escalation_reason == "critical_sentiment":
        actions.insert(0, "Customer is frustrated - acknowledge their concern first")
    elif escalation_reason == "loop_detected":
        actions.insert(0, "Customer's query was not resolved by bot - clarify their need")
    elif escalation_reason == "explicit_request":
        actions.insert(0, "Customer specifically requested human assistance")

    if not actions:
        actions.append("Understand customer's specific need and assist accordingly")

    return actions