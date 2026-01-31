"""Conversation logging service - stores to database and S3."""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json

from .s3_service import upload_conversation_to_s3

logger = logging.getLogger(__name__)


class ConversationLogService:
    """Service for logging conversations to database and S3."""

    async def start_conversation(
        self,
        db: AsyncSession,
        session_id: str,
        phone_number: str,
        channel: str = "voice",
        driver_id: str = None,
        driver_name: str = None,
        call_sid: str = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Start a new conversation log.

        Args:
            db: Database session
            session_id: Unique session identifier
            phone_number: Driver's phone number
            channel: Communication channel (voice, chat, sms)
            driver_id: Optional driver UUID
            driver_name: Optional driver name
            call_sid: Optional Twilio call SID
            metadata: Optional additional metadata

        Returns:
            Created conversation log record
        """
        try:
            query = text("""
                INSERT INTO conversation_logs (
                    session_id, phone_number, channel, driver_id, started_at
                ) VALUES (
                    :session_id, :phone_number, :channel, :driver_id, NOW()
                )
                ON CONFLICT (session_id) DO UPDATE SET
                    updated_at = NOW()
                RETURNING id, session_id, started_at
            """)

            result = await db.execute(query, {
                "session_id": session_id,
                "phone_number": phone_number,
                "channel": channel,
                "driver_id": driver_id,
                "driver_name": driver_name,
                "call_sid": call_sid,
                "metadata": json.dumps(metadata or {})
            })
            await db.commit()

            row = result.fetchone()
            logger.info(f"Started conversation log: {session_id}")

            return {
                "id": str(row[0]),
                "session_id": row[1],
                "started_at": row[2].isoformat() if row[2] else None
            }

        except Exception as e:
            logger.error(f"Error starting conversation log: {e}")
            await db.rollback()
            return {"session_id": session_id, "error": str(e)}

    async def add_turn(
        self,
        db: AsyncSession,
        session_id: str,
        role: str,
        message: str,
        intent: str = None,
        confidence: float = None,
        entities: Dict[str, Any] = None,
        sentiment: float = None,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Add a conversation turn.

        Args:
            db: Database session
            session_id: Session identifier
            role: 'user' or 'bot'
            message: The message text
            intent: Detected intent (for user messages)
            confidence: Intent confidence score
            entities: Extracted entities
            sentiment: Sentiment score

        Returns:
            True if successful
        """
        try:
            turn = {
                "role": role,
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
                "intent": intent,
                "confidence": confidence,
                "entities": entities,
                "sentiment": sentiment
            }

            query = text("""
                UPDATE conversation_logs
                SET
                    turns = turns || CAST(:turn AS jsonb),
                    turn_count = turn_count + 1,
                    intents_detected = CASE
                        WHEN CAST(:intent AS text) IS NOT NULL AND NOT (CAST(:intent AS text) = ANY(COALESCE(intents_detected, ARRAY[]::text[])))
                        THEN array_append(COALESCE(intents_detected, ARRAY[]::text[]), CAST(:intent AS text))
                        ELSE intents_detected
                    END,
                    updated_at = NOW()
                WHERE session_id = :session_id
            """)

            await db.execute(query, {
                "session_id": session_id,
                "turn": json.dumps(turn),
                "intent": intent
            })
            await db.commit()

            logger.debug(f"Added turn to conversation {session_id}: {role}")
            return True

        except Exception as e:
            logger.error(f"Error adding turn: {e}")
            await db.rollback()
            return False

    async def end_conversation(
        self,
        db: AsyncSession,
        session_id: str,
        resolution_status: str = "resolved",
        escalated: bool = False,
        escalation_reason: str = None,
        primary_intent: str = None,
        sentiment_score: float = None,
        avg_confidence: float = None
    ) -> Optional[Dict[str, Any]]:
        """
        End a conversation and upload to S3.

        Args:
            db: Database session
            session_id: Session identifier
            resolution_status: resolved, escalated, abandoned
            escalated: Whether call was escalated to human
            escalation_reason: Reason for escalation
            primary_intent: Main intent of the conversation
            sentiment_score: Overall sentiment score
            avg_confidence: Average confidence across turns

        Returns:
            Conversation summary with S3 details
        """
        try:
            # First, get the full conversation data
            fetch_query = text("""
           SELECT
                    cl.id, session_id, cl.phone_number, driver_id, d.driver_name ,
                    channel, started_at,
                    intents_detected
                FROM conversation_logs cl
                left join drivers d on d.id = cl.driver_id  
                WHERE session_id = :session_id
            """)

            result = await db.execute(fetch_query, {"session_id": session_id})
            row = result.fetchone()

            if not row:
                logger.warning(f"Conversation not found: {session_id}")
                return None

            data = dict(row._mapping)
            started_at = data["started_at"]
            ended_at = datetime.utcnow()
            duration = int((ended_at - started_at).total_seconds()) if started_at else 0

            # Prepare full conversation data for S3
            conversation_data = {
                "session_id": session_id,
                "phone_number": data["phone_number"],
                "driver_id": str(data["driver_id"]) if data["driver_id"] else None,
                "driver_name": data["driver_name"],
                "channel": data["channel"],
                "started_at": started_at.isoformat() if started_at else None,
                "ended_at": ended_at.isoformat(),
                "duration_seconds": duration,
                "intents_detected": data["intents_detected"] or [],
                "primary_intent": primary_intent,
                "resolution_status": resolution_status,
                "escalated_to_human": escalated,
                "escalation_reason": escalation_reason,
                "sentiment_score": sentiment_score,
                "avg_confidence": avg_confidence,
                "metadata": data["metadata"] if isinstance(data["metadata"], dict) else json.loads(data["metadata"] or "{}")
            }

            # Upload to S3
            s3_result = await upload_conversation_to_s3(
                session_id=session_id,
                phone_number=data["phone_number"],
                conversation_data=conversation_data
            )

            # Update database record
            update_query = text("""
                UPDATE conversation_logs
                SET
                    ended_at = :ended_at,
                    duration_seconds = :duration,
                    resolution_status = :resolution_status,
                    escalated_to_human = :escalated,
                    escalation_reason = :escalation_reason,
                    primary_intent = :primary_intent,
                    sentiment_score = :sentiment_score,
                    avg_confidence = :avg_confidence,
                    s3_bucket = :s3_bucket,
                    s3_key = :s3_key,
                    s3_url = :s3_url,
                    updated_at = NOW()
                WHERE session_id = :session_id
                RETURNING id, duration_seconds, turn_count
            """)

            result = await db.execute(update_query, {
                "session_id": session_id,
                "ended_at": ended_at,
                "duration": duration,
                "resolution_status": resolution_status,
                "escalated": escalated,
                "escalation_reason": escalation_reason,
                "primary_intent": primary_intent,
                "sentiment_score": sentiment_score,
                "avg_confidence": avg_confidence,
                "s3_bucket": s3_result["bucket"] if s3_result else None,
                "s3_key": s3_result["key"] if s3_result else None,
                "s3_url": s3_result["url"] if s3_result else None
            })
            await db.commit()

            final = result.fetchone()
            logger.info(f"Ended conversation {session_id}: {resolution_status}, duration={duration}s")

            return {
                "session_id": session_id,
                "duration_seconds": duration,
                "turn_count": final[2] if final else data["turn_count"],
                "resolution_status": resolution_status,
                "s3_url": s3_result["url"] if s3_result else None
            }

        except Exception as e:
            logger.error(f"Error ending conversation: {e}")
            await db.rollback()
            return None

    async def get_conversation(
        self,
        db: AsyncSession,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get full conversation log by session ID."""
        try:
            query = text("""
                SELECT * FROM conversation_logs
                WHERE session_id = :session_id
            """)
            result = await db.execute(query, {"session_id": session_id})
            row = result.fetchone()

            if row:
                return dict(row._mapping)
            return None

        except Exception as e:
            logger.error(f"Error getting conversation: {e}")
            return None

    async def get_driver_conversations(
        self,
        db: AsyncSession,
        phone_number: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent conversations for a driver."""
        try:
            query = text("""
                SELECT
                    session_id, channel, started_at, ended_at,
                    duration_seconds, turn_count, primary_intent,
                    resolution_status, sentiment_score
                FROM conversation_logs
                WHERE phone_number = :phone_number
                ORDER BY started_at DESC
                LIMIT :limit
            """)
            result = await db.execute(query, {
                "phone_number": phone_number,
                "limit": limit
            })
            rows = result.fetchall()

            return [dict(row._mapping) for row in rows]

        except Exception as e:
            logger.error(f"Error getting driver conversations: {e}")
            return []


# Singleton instance
conversation_log_service = ConversationLogService()


# Helper functions
async def start_conversation_log(
    db: AsyncSession,
    session_id: str,
    phone_number: str,
    **kwargs
) -> Dict[str, Any]:
    """Start a new conversation log."""
    return await conversation_log_service.start_conversation(
        db, session_id, phone_number, **kwargs
    )


async def add_conversation_turn(
    db: AsyncSession,
    session_id: str,
    role: str,
    message: str,
    **kwargs
) -> bool:
    """Add a turn to the conversation."""
    return await conversation_log_service.add_turn(
        db, session_id, role, message, **kwargs
    )


async def end_conversation_log(
    db: AsyncSession,
    session_id: str,
    **kwargs
) -> Optional[Dict[str, Any]]:
    """End a conversation and save to S3."""
    return await conversation_log_service.end_conversation(
        db, session_id, **kwargs
    )