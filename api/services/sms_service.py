"""SMS service for sending messages via Twilio."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# Initialize Twilio client
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


async def send_sms(
    db: AsyncSession,
    phone_number: str,
    message: str,
    message_type: str,
    user_id: str = None
) -> dict:
    """Send SMS via Twilio and log to database."""
    if not twilio_client:
        logger.error("Twilio client not initialized")
        return {
            "success": False,
            "error": "SMS service not configured",
            "message": message
        }

    # Format phone number for India
    formatted_phone = phone_number
    if not phone_number.startswith("+"):
        if phone_number.startswith("91"):
            formatted_phone = f"+{phone_number}"
        else:
            formatted_phone = f"+91{phone_number}"

    try:
        # Send SMS via Twilio
        message_response = twilio_client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=formatted_phone
        )

        # Log to database
        await log_sms(
            db=db,
            user_id=user_id,
            phone_number=phone_number,
            message_type=message_type,
            message_content=message,
            twilio_sid=message_response.sid,
            status="sent"
        )

        return {
            "success": True,
            "sid": message_response.sid,
            "status": message_response.status,
            "message": message
        }

    except TwilioRestException as e:
        logger.error(f"Twilio error: {e}")
        await log_sms(
            db=db,
            user_id=user_id,
            phone_number=phone_number,
            message_type=message_type,
            message_content=message,
            twilio_sid=None,
            status="failed",
            error_message=str(e)
        )
        return {
            "success": False,
            "error": str(e),
            "message": message
        }
    except Exception as e:
        logger.error(f"SMS error: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": message
        }


async def log_sms(
    db: AsyncSession,
    user_id: str,
    phone_number: str,
    message_type: str,
    message_content: str,
    twilio_sid: str = None,
    status: str = "pending",
    error_message: str = None
):
    """Log SMS to database."""
    try:
        query = text("""
            INSERT INTO sms_logs (user_id, phone_number, message_type, message_content, twilio_sid, status, error_message)
            VALUES (:user_id, :phone_number, :message_type, :message_content, :twilio_sid, :status, :error_message)
            RETURNING id
        """)
        await db.execute(query, {
            "user_id": user_id,
            "phone_number": phone_number,
            "message_type": message_type,
            "message_content": message_content,
            "twilio_sid": twilio_sid,
            "status": status,
            "error_message": error_message
        })
        await db.commit()
    except Exception as e:
        logger.error(f"Error logging SMS: {e}")


async def send_swap_history_sms(
    db: AsyncSession,
    phone_number: str,
    swaps: list,
    time_period: str,
    user_id: str = None
) -> dict:
    """Send swap history summary via SMS."""
    if not swaps:
        message = "Battery Smart: Aapki swap history mein koi record nahi mila."
    else:
        period_text = {
            "today": "aaj",
            "yesterday": "kal",
            "last_week": "is hafte",
            "last_month": "is mahine"
        }.get(time_period, time_period)

        total_swaps = len(swaps)
        message = f"Battery Smart: {period_text.title()} ke {total_swaps} swaps:\n\n"

        for i, swap in enumerate(swaps[:5], 1):  # Limit to 5 in SMS
            swap_time = swap.get("swap_time", "")
            if isinstance(swap_time, datetime):
                swap_time = swap_time.strftime("%d/%m %H:%M")
            station = swap.get("station_name", "Unknown")
            message += f"{i}. {swap_time} - {station}\n"

        if total_swaps > 5:
            message += f"\n...aur {total_swaps - 5} more swaps"

    return await send_sms(db, phone_number, message, "swap_history", user_id)


async def send_payment_link_sms(
    db: AsyncSession,
    phone_number: str,
    payment_link: str,
    plan_name: str,
    amount: float,
    user_id: str = None
) -> dict:
    """Send payment link via SMS."""
    message = (
        f"Battery Smart: {plan_name} plan ke liye Rs.{amount:.0f} ka payment link:\n\n"
        f"{payment_link}\n\n"
        f"Link 24 ghante tak valid hai."
    )
    return await send_sms(db, phone_number, message, "payment_link", user_id)


async def send_subscription_confirmation_sms(
    db: AsyncSession,
    phone_number: str,
    plan_name: str,
    start_date: str,
    end_date: str,
    amount: float,
    user_id: str = None
) -> dict:
    """Send subscription confirmation via SMS."""
    message = (
        f"Battery Smart: Aapka {plan_name} plan activate ho gaya!\n\n"
        f"Start: {start_date}\n"
        f"End: {end_date}\n"
        f"Amount: Rs.{amount:.0f}\n\n"
        f"Happy Riding!"
    )
    return await send_sms(db, phone_number, message, "subscription_confirmation", user_id)


async def send_invoice_sms(
    db: AsyncSession,
    phone_number: str,
    invoice_number: str,
    amount: float,
    description: str,
    user_id: str = None
) -> dict:
    """Send invoice details via SMS."""
    message = (
        f"Battery Smart Invoice\n\n"
        f"Invoice: {invoice_number}\n"
        f"Amount: Rs.{amount:.0f}\n"
        f"Details: {description}\n\n"
        f"Questions? Call our helpline."
    )
    return await send_sms(db, phone_number, message, "invoice", user_id)


async def send_penalty_notification_sms(
    db: AsyncSession,
    phone_number: str,
    days_overdue: int,
    penalty_amount: float,
    user_id: str = None
) -> dict:
    """Send penalty notification via SMS."""
    message = (
        f"Battery Smart Alert!\n\n"
        f"Aapki battery return nahi hui hai.\n"
        f"Overdue: {days_overdue} din\n"
        f"Penalty: Rs.{penalty_amount:.0f} (Rs.80/din)\n\n"
        f"Kripya jaldi se battery return karein."
    )
    return await send_sms(db, phone_number, message, "penalty_notification", user_id)