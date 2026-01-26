"""Amazon Connect integration handler for voice calls."""
import os
import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# AWS Configuration
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
CONNECT_INSTANCE_ID = os.getenv("CONNECT_INSTANCE_ID")
CONNECT_CONTACT_FLOW_ID = os.getenv("CONNECT_CONTACT_FLOW_ID")
CONNECT_QUEUE_ID = os.getenv("CONNECT_QUEUE_ID")


@dataclass
class ContactAttributes:
    """Attributes passed with Amazon Connect contact."""
    phone_number: str
    session_id: str
    driver_name: Optional[str] = None
    driver_language: str = "hi-en"
    escalation_reason: Optional[str] = None
    sentiment_score: float = 0.0
    conversation_summary: Optional[str] = None


class AmazonConnectHandler:
    """Handler for Amazon Connect operations."""

    def __init__(
        self,
        instance_id: str = None,
        contact_flow_id: str = None,
        queue_id: str = None,
        region: str = None
    ):
        self.instance_id = instance_id or CONNECT_INSTANCE_ID
        self.contact_flow_id = contact_flow_id or CONNECT_CONTACT_FLOW_ID
        self.queue_id = queue_id or CONNECT_QUEUE_ID
        self.region = region or AWS_REGION

        self.client = boto3.client(
            "connect",
            region_name=self.region
        )

    def parse_contact_event(self, event: Dict[str, Any]) -> ContactAttributes:
        """Parse incoming contact event from Amazon Connect."""
        details = event.get("Details", {})
        contact_data = details.get("ContactData", {})
        attributes = contact_data.get("Attributes", {})
        customer_endpoint = contact_data.get("CustomerEndpoint", {})

        phone_number = customer_endpoint.get("Address", "")
        # Clean phone number
        phone_number = phone_number.replace("+91", "").replace(" ", "").strip()
        if len(phone_number) > 10:
            phone_number = phone_number[-10:]

        return ContactAttributes(
            phone_number=phone_number,
            session_id=contact_data.get("ContactId", ""),
            driver_name=attributes.get("driver_name"),
            driver_language=attributes.get("language", "hi-en"),
            escalation_reason=attributes.get("escalation_reason"),
            sentiment_score=float(attributes.get("sentiment_score", 0)),
            conversation_summary=attributes.get("conversation_summary")
        )

    def update_contact_attributes(
        self,
        contact_id: str,
        attributes: Dict[str, str]
    ) -> bool:
        """Update contact attributes in Amazon Connect."""
        try:
            self.client.update_contact_attributes(
                InstanceId=self.instance_id,
                InitialContactId=contact_id,
                Attributes=attributes
            )
            return True
        except ClientError as e:
            logger.error(f"Error updating contact attributes: {e}")
            return False

    def transfer_to_queue(
        self,
        contact_id: str,
        queue_id: str = None,
        summary: Dict[str, Any] = None
    ) -> bool:
        """Transfer contact to agent queue with summary."""
        queue_id = queue_id or self.queue_id

        try:
            # First update attributes with handoff summary
            if summary:
                attributes = {
                    "handoff_summary": json.dumps(summary, default=str),
                    "driver_name": summary.get("driver_name", ""),
                    "driver_phone": summary.get("phone_number", ""),
                    "escalation_reason": summary.get("escalation_trigger", ""),
                    "sentiment_score": str(summary.get("sentiment_score", 0)),
                    "conversation_summary": summary.get("conversation_summary", "")[:200]
                }
                self.update_contact_attributes(contact_id, attributes)

            # Transfer to queue
            self.client.transfer_contact(
                InstanceId=self.instance_id,
                ContactId=contact_id,
                QueueId=queue_id
            )

            logger.info(f"Transferred contact {contact_id} to queue {queue_id}")
            return True

        except ClientError as e:
            logger.error(f"Error transferring contact: {e}")
            return False

    def start_outbound_voice_contact(
        self,
        destination_phone: str,
        source_phone: str,
        attributes: Dict[str, str] = None
    ) -> Optional[str]:
        """Start an outbound voice contact."""
        try:
            response = self.client.start_outbound_voice_contact(
                InstanceId=self.instance_id,
                ContactFlowId=self.contact_flow_id,
                DestinationPhoneNumber=f"+91{destination_phone}",
                SourcePhoneNumber=source_phone,
                Attributes=attributes or {}
            )
            return response.get("ContactId")

        except ClientError as e:
            logger.error(f"Error starting outbound contact: {e}")
            return None

    def stop_contact(self, contact_id: str) -> bool:
        """Stop/disconnect a contact."""
        try:
            self.client.stop_contact(
                InstanceId=self.instance_id,
                ContactId=contact_id
            )
            return True
        except ClientError as e:
            logger.error(f"Error stopping contact: {e}")
            return False

    def get_current_metric_data(self) -> Dict[str, Any]:
        """Get current queue metrics."""
        try:
            response = self.client.get_current_metric_data(
                InstanceId=self.instance_id,
                Filters={
                    "Queues": [self.queue_id],
                    "Channels": ["VOICE"]
                },
                CurrentMetrics=[
                    {"Name": "AGENTS_AVAILABLE", "Unit": "COUNT"},
                    {"Name": "CONTACTS_IN_QUEUE", "Unit": "COUNT"},
                    {"Name": "OLDEST_CONTACT_AGE", "Unit": "SECONDS"}
                ]
            )

            metrics = {}
            for collection in response.get("MetricResults", []):
                for metric in collection.get("Collections", []):
                    name = metric.get("Metric", {}).get("Name")
                    value = metric.get("Value")
                    if name:
                        metrics[name] = value

            return metrics

        except ClientError as e:
            logger.error(f"Error getting metrics: {e}")
            return {}


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    AWS Lambda handler for Amazon Connect integration.

    This function is invoked by Amazon Connect contact flows.
    """
    logger.info(f"Received event: {json.dumps(event)}")

    handler = AmazonConnectHandler()

    # Parse contact information
    contact = handler.parse_contact_event(event)

    # Determine action based on event type
    action = event.get("Name", "")

    if action == "StartSession":
        # New call - start voice session
        return {
            "session_id": contact.session_id,
            "phone_number": contact.phone_number,
            "greeting": "Namaste! Battery Smart mein aapka swagat hai.",
            "language": contact.driver_language
        }

    elif action == "ProcessInput":
        # Process user input - handled by voice orchestrator
        return {
            "status": "processing",
            "session_id": contact.session_id
        }

    elif action == "Handoff":
        # Transfer to human agent
        summary = json.loads(event.get("Details", {}).get("Parameters", {}).get("summary", "{}"))
        success = handler.transfer_to_queue(contact.session_id, summary=summary)
        return {
            "status": "transferred" if success else "error",
            "session_id": contact.session_id
        }

    elif action == "EndSession":
        # End the session
        return {
            "status": "ended",
            "session_id": contact.session_id,
            "farewell": "Dhanyavaad! Battery Smart ko choose karne ke liye shukriya."
        }

    else:
        return {
            "status": "unknown_action",
            "action": action
        }