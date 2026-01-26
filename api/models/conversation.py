"""Conversation and analytics models."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from decimal import Decimal


class ConversationStart(BaseModel):
    """Model for starting a conversation."""
    phone_number: str = Field(..., pattern=r"^[6-9]\d{9}$")
    channel: str = Field(default="voice", pattern=r"^(voice|chat|sms)$")
    session_id: Optional[str] = None


class ConversationStartResponse(BaseModel):
    """Response when conversation starts."""
    session_id: str
    driver_id: Optional[UUID]
    driver_name: Optional[str]
    preferred_language: str
    is_new_driver: bool
    greeting: str
    greeting_hi: str


class ConversationTurn(BaseModel):
    """Model for a conversation turn."""
    session_id: str
    role: str = Field(..., pattern=r"^(user|bot)$")
    message: str
    intent: Optional[str] = None
    intent_confidence: Optional[float] = None
    entities: Optional[Dict[str, Any]] = None
    sentiment_score: Optional[float] = None


class SentimentAnalysis(BaseModel):
    """Model for sentiment analysis result."""
    score: float = Field(..., ge=-1.0, le=1.0)
    emotion: str
    escalate: bool
    confidence: float


class ConfidenceCheck(BaseModel):
    """Model for confidence check result."""
    intent_confidence: float
    cumulative_confidence: float
    low_confidence_turns: int
    suggest_handoff: bool
    reason: Optional[str] = None


class EscalationTrigger(BaseModel):
    """Model for escalation trigger."""
    should_escalate: bool
    trigger_type: Optional[str] = None
    trigger_reason: Optional[str] = None
    confidence_score: float
    sentiment_score: float


class HandoffSummary(BaseModel):
    """Model for agent handoff summary."""
    session_id: str
    phone_number: str
    driver_name: Optional[str]
    driver_language: str
    registration_date: Optional[datetime]

    # Subscription info
    plan_name: Optional[str]
    plan_status: Optional[str]
    plan_expiry: Optional[str]
    monthly_swaps: int

    # Recent activity
    last_swap_time: Optional[str]
    last_swap_station: Optional[str]
    pending_issues: Optional[str]

    # Conversation context
    conversation_summary: str
    intents_detected: List[str]
    duration_seconds: int
    turns_count: int

    # Escalation info
    escalation_trigger: str
    confidence_score: float
    sentiment_score: float
    detected_emotion: str

    # Recommendations
    recommended_actions: List[str]


class ConversationEnd(BaseModel):
    """Model for ending a conversation."""
    session_id: str
    resolution_status: str = Field(
        ...,
        pattern=r"^(resolved|escalated|abandoned)$"
    )
    handoff_occurred: bool = False
    handoff_reason: Optional[str] = None


class ConversationEndResponse(BaseModel):
    """Response when conversation ends."""
    session_id: str
    duration_seconds: int
    turns_count: int
    resolution_status: str
    summary: Optional[str] = None
    farewell: str
    farewell_hi: str