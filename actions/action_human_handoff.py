from typing import Any, Dict, List, Text
import logging

import openai
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict

logger = logging.getLogger(__name__)


class ActionHumanHandoff(Action):
    def name(self) -> Text:
        return "action_human_handoff"

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        logger.info("Executing action_human_handoff - initiating call transfer")

        # Build conversation summary
        convo: List[str] = []
        for event in tracker.events:
            if event.get("event") == "user":
                user_text = str(event.get("text") or "")
                convo.append(f"user - {user_text}")
            elif event.get("event") == "bot":
                bot_text = str(event.get("text") or "")
                convo.append(f"bot - {bot_text}")

        summarised_conversation = "No summary available"
        try:
            prompt = (
                f"The following is a conversation between a bot and a human user. "
                f"Please summarise so that a human agent can easily understand the "
                f"important context. Conversation: "
                f"{convo}"
            )
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
            )
            summarised_conversation = (
                response.choices[0].message.content or "No summary available"
            )
        except Exception as e:
            logger.error(f"Failed to generate conversation summary: {e}")

        # Send custom JSON with handoff action - this triggers call forwarding in voice orchestrator
        dispatcher.utter_message(
            json_message={
                "action": "handoff",
                "summary": summarised_conversation,
                "reason": "user_requested"
            }
        )

        return []
