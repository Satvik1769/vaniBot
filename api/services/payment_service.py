"""Payment service for Razorpay integration."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
import httpx
import razorpay
import os
import uuid
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

# Razorpay configuration
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

# GST rate
GST_RATE = Decimal("0.18")

# Initialize Razorpay client
razorpay_client = None
if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


class RazorpayPaymentService:
    """Handle Razorpay payment operations."""

    def __init__(self):
        self.client = razorpay_client
        self.key_id = RAZORPAY_KEY_ID

    async def create_payment_link(
        self,
        db: AsyncSession,
        user_id: str,
        plan_id: str,
        amount: Decimal,
        phone_number: str,
        customer_name: str = None,
        customer_email: str = None
    ) -> dict:
        """Create a Razorpay payment link and return it."""
        # Generate unique reference ID
        reference_id = f"BSMART-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8].upper()}"

        # Calculate tax
        tax_amount = amount * GST_RATE
        total_amount = amount + tax_amount
        # Razorpay expects amount in paise (smallest currency unit)
        amount_in_paise = int(total_amount * 100)

        # Create transaction record in database first
        await self._create_transaction_record(
            db=db,
            user_id=user_id,
            plan_id=plan_id,
            order_id=reference_id,
            amount=amount,
            tax_amount=tax_amount,
            total_amount=total_amount
        )

        if not self.client:
            # Return mock payment link for development
            return await self._create_mock_payment_link(
                db, reference_id, amount, tax_amount, total_amount, phone_number
            )

        try:
            # Create Razorpay Payment Link
            payment_link_data = {
                "amount": amount_in_paise,
                "currency": "INR",
                "accept_partial": False,
                "reference_id": reference_id,
                "description": f"Battery Smart Subscription",
                "customer": {
                    "name": customer_name or "Battery Smart User",
                    "contact": f"+91{phone_number}" if not phone_number.startswith("+") else phone_number,
                    "email": customer_email or f"{phone_number}@batterysmart.in"
                },
                "notify": {
                    "sms": True,
                    "email": False
                },
                "reminder_enable": True,
                "expire_by": int((datetime.now() + timedelta(hours=24)).timestamp()),
                "notes": {
                    "user_id": user_id,
                    "plan_id": plan_id,
                    "phone_number": phone_number
                }
            }

            payment_link = self.client.payment_link.create(payment_link_data)

            # Update transaction with Razorpay response
            await self._update_transaction(
                db=db,
                order_id=reference_id,
                gateway_response=payment_link,
                gateway_transaction_id=payment_link.get("id"),
                status="payment_link_created"
            )

            return {
                "success": True,
                "order_id": reference_id,
                "razorpay_payment_link_id": payment_link.get("id"),
                "payment_link": payment_link.get("short_url"),
                "amount": float(amount),
                "tax_amount": float(tax_amount),
                "total_amount": float(total_amount),
                "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
            }

        except razorpay.errors.BadRequestError as e:
            logger.error(f"Razorpay BadRequest: {e}")
            return {
                "success": False,
                "error": str(e),
                "order_id": reference_id
            }
        except Exception as e:
            logger.error(f"Razorpay error: {e}")
            # Fallback to mock for development
            return await self._create_mock_payment_link(
                db, reference_id, amount, tax_amount, total_amount, phone_number
            )

    async def create_order(
        self,
        db: AsyncSession,
        user_id: str,
        plan_id: str,
        amount: Decimal,
        phone_number: str,
        customer_email: str = None
    ) -> dict:
        """Create a Razorpay order (for custom checkout integration)."""
        reference_id = f"BSMART-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8].upper()}"

        # Calculate tax
        tax_amount = amount * GST_RATE
        total_amount = amount + tax_amount
        amount_in_paise = int(total_amount * 100)

        # Create transaction record
        await self._create_transaction_record(
            db=db,
            user_id=user_id,
            plan_id=plan_id,
            order_id=reference_id,
            amount=amount,
            tax_amount=tax_amount,
            total_amount=total_amount
        )

        if not self.client:
            return await self._create_mock_payment_link(
                db, reference_id, amount, tax_amount, total_amount, phone_number
            )

        try:
            # Create Razorpay Order
            order_data = {
                "amount": amount_in_paise,
                "currency": "INR",
                "receipt": reference_id,
                "notes": {
                    "user_id": user_id,
                    "plan_id": plan_id,
                    "phone_number": phone_number
                }
            }

            order = self.client.order.create(order_data)

            await self._update_transaction(
                db=db,
                order_id=reference_id,
                gateway_response=order,
                gateway_transaction_id=order.get("id"),
                status="order_created"
            )

            return {
                "success": True,
                "order_id": reference_id,
                "razorpay_order_id": order.get("id"),
                "razorpay_key_id": self.key_id,
                "amount": float(amount),
                "tax_amount": float(tax_amount),
                "total_amount": float(total_amount),
                "amount_in_paise": amount_in_paise,
                "currency": "INR"
            }

        except Exception as e:
            logger.error(f"Razorpay order error: {e}")
            return {
                "success": False,
                "error": str(e),
                "order_id": reference_id
            }

    async def _create_mock_payment_link(
        self,
        db: AsyncSession,
        order_id: str,
        amount: Decimal,
        tax_amount: Decimal,
        total_amount: Decimal,
        phone_number: str
    ) -> dict:
        """Create a mock payment link for development/testing."""
        mock_link = f"https://pay.batterysmart.in/order/{order_id}"

        await self._update_transaction(
            db=db,
            order_id=order_id,
            gateway_response={"mock": True, "link": mock_link},
            status="payment_link_created"
        )

        return {
            "success": True,
            "order_id": order_id,
            "payment_link": mock_link,
            "amount": float(amount),
            "tax_amount": float(tax_amount),
            "total_amount": float(total_amount),
            "expires_at": (datetime.now() + timedelta(hours=24)).isoformat(),
            "is_mock": True
        }

    async def verify_payment(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str
    ) -> bool:
        """Verify Razorpay payment signature."""
        if not self.client:
            return True  # Mock verification for development

        try:
            self.client.utility.verify_payment_signature({
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature
            })
            return True
        except razorpay.errors.SignatureVerificationError:
            return False

    async def check_payment_status(self, db: AsyncSession, order_id: str) -> dict:
        """Check payment status from database or Razorpay."""
        # First check database
        query = text("""
            SELECT order_id, status, gateway_transaction_id, payment_date, gateway_response
            FROM transaction_history
            WHERE order_id = :order_id
        """)
        result = await db.execute(query, {"order_id": order_id})
        row = result.fetchone()

        if not row:
            return {
                "success": False,
                "order_id": order_id,
                "status": "not_found",
                "error": "Transaction not found"
            }

        data = dict(row._mapping)
        gateway_response = data.get("gateway_response")

        # If we have a Razorpay payment link ID, check its status
        if self.client and gateway_response:
            try:
                response_data = json.loads(gateway_response) if isinstance(gateway_response, str) else gateway_response
                payment_link_id = response_data.get("id")

                if payment_link_id and payment_link_id.startswith("plink_"):
                    link_status = self.client.payment_link.fetch(payment_link_id)
                    status = link_status.get("status")

                    status_map = {
                        "created": "pending",
                        "partially_paid": "pending",
                        "paid": "completed",
                        "cancelled": "failed",
                        "expired": "failed"
                    }
                    our_status = status_map.get(status, "pending")

                    if our_status != data["status"]:
                        await self._update_transaction(
                            db=db,
                            order_id=order_id,
                            status=our_status,
                            payment_date=datetime.now() if our_status == "completed" else None
                        )

                        if our_status == "completed":
                            await self._activate_subscription_from_transaction(db, order_id)

                    return {
                        "success": True,
                        "order_id": order_id,
                        "status": our_status,
                        "razorpay_status": status,
                        "payment_link_id": payment_link_id
                    }
            except Exception as e:
                logger.error(f"Error checking Razorpay status: {e}")

        return {
            "success": True,
            "order_id": order_id,
            "status": data["status"],
            "transaction_id": data.get("gateway_transaction_id")
        }

    async def handle_webhook(self, db: AsyncSession, payload: dict, signature: str) -> dict:
        """Handle Razorpay webhook callback."""
        # Verify webhook signature
        if RAZORPAY_WEBHOOK_SECRET and signature:
            expected_signature = hmac.new(
                RAZORPAY_WEBHOOK_SECRET.encode(),
                json.dumps(payload, separators=(',', ':')).encode(),
                hashlib.sha256
            ).hexdigest()

            if signature != expected_signature:
                logger.warning("Invalid webhook signature")
                return {"success": False, "error": "Invalid signature"}

        event = payload.get("event")
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        payment_link_entity = payload.get("payload", {}).get("payment_link", {}).get("entity", {})

        # Get reference_id from notes
        notes = payment_entity.get("notes", {}) or payment_link_entity.get("notes", {})
        order_id = notes.get("reference_id") or payment_link_entity.get("reference_id")

        if not order_id:
            # Try to find by razorpay payment link id
            plink_id = payment_link_entity.get("id")
            if plink_id:
                query = text("""
                    SELECT order_id FROM transaction_history
                    WHERE gateway_response::text LIKE :plink_pattern
                """)
                result = await db.execute(query, {"plink_pattern": f"%{plink_id}%"})
                row = result.fetchone()
                if row:
                    order_id = row[0]

        if not order_id:
            logger.warning(f"Order ID not found in webhook payload: {event}")
            return {"success": False, "error": "Order ID not found"}

        # Handle different events
        if event in ["payment.captured", "payment_link.paid"]:
            await self._update_transaction(
                db=db,
                order_id=order_id,
                status="completed",
                gateway_transaction_id=payment_entity.get("id"),
                payment_date=datetime.now()
            )
            await self._activate_subscription_from_transaction(db, order_id)
            return {"success": True, "order_id": order_id, "status": "completed"}

        elif event in ["payment.failed", "payment_link.cancelled", "payment_link.expired"]:
            await self._update_transaction(
                db=db,
                order_id=order_id,
                status="failed"
            )
            return {"success": True, "order_id": order_id, "status": "failed"}

        return {"success": True, "order_id": order_id, "event": event}

    async def _create_transaction_record(
        self,
        db: AsyncSession,
        user_id: str,
        plan_id: str,
        order_id: str,
        amount: Decimal,
        tax_amount: Decimal,
        total_amount: Decimal
    ):
        """Create transaction record in database."""
        query = text("""
            INSERT INTO transaction_history
            (user_id, plan_id, order_id, amount, tax_amount, total_amount, status, payment_gateway)
            VALUES (:user_id, :plan_id, :order_id, :amount, :tax_amount, :total_amount, 'pending', 'razorpay')
            RETURNING id
        """)
        await db.execute(query, {
            "user_id": user_id,
            "plan_id": plan_id,
            "order_id": order_id,
            "amount": amount,
            "tax_amount": tax_amount,
            "total_amount": total_amount
        })
        await db.commit()

    async def _update_transaction(
        self,
        db: AsyncSession,
        order_id: str,
        gateway_response: dict = None,
        status: str = None,
        gateway_transaction_id: str = None,
        payment_date: datetime = None
    ):
        """Update transaction record."""
        updates = []
        params = {"order_id": order_id}

        if gateway_response:
            updates.append("gateway_response = :gateway_response")
            params["gateway_response"] = json.dumps(gateway_response)
        if status:
            updates.append("status = :status")
            params["status"] = status
        if gateway_transaction_id:
            updates.append("gateway_transaction_id = :gateway_transaction_id")
            params["gateway_transaction_id"] = gateway_transaction_id
        if payment_date:
            updates.append("payment_date = :payment_date")
            params["payment_date"] = payment_date

        if updates:
            query = text(f"""
                UPDATE transaction_history
                SET {', '.join(updates)}
                WHERE order_id = :order_id
            """)
            await db.execute(query, params)
            await db.commit()

    async def _activate_subscription_from_transaction(self, db: AsyncSession, order_id: str):
        """Activate subscription after successful payment."""
        # Get transaction details
        query = text("""
            SELECT th.user_id, th.plan_id, sp.validity_days
            FROM transaction_history th
            JOIN subscription_plans sp ON th.plan_id = sp.id
            WHERE th.order_id = :order_id
        """)
        result = await db.execute(query, {"order_id": order_id})
        row = result.fetchone()

        if not row:
            logger.error(f"Transaction not found for order: {order_id}")
            return

        data = dict(row._mapping)

        # Create or update subscription
        today = datetime.now().date()
        end_date = today + timedelta(days=data["validity_days"])

        # Check for existing active subscription
        check_query = text("""
            SELECT id, end_date FROM driver_subscriptions
            WHERE driver_id = :user_id AND status = 'active'
        """)
        existing = await db.execute(check_query, {"user_id": data["user_id"]})
        existing_row = existing.fetchone()

        if existing_row:
            # Extend existing subscription from current end_date
            current_end = existing_row[1]
            if current_end > today:
                end_date = current_end + timedelta(days=data["validity_days"])

            update_query = text("""
                UPDATE driver_subscriptions
                SET end_date = :end_date, plan_id = :plan_id, updated_at = NOW()
                WHERE id = :sub_id
            """)
            await db.execute(update_query, {
                "end_date": end_date,
                "plan_id": data["plan_id"],
                "sub_id": existing_row[0]
            })
        else:
            # Create new subscription
            insert_query = text("""
                INSERT INTO driver_subscriptions
                (driver_id, plan_id, start_date, end_date, status)
                VALUES (:user_id, :plan_id, :start_date, :end_date, 'active')
            """)
            await db.execute(insert_query, {
                "user_id": data["user_id"],
                "plan_id": data["plan_id"],
                "start_date": today,
                "end_date": end_date
            })

        await db.commit()
        logger.info(f"Subscription activated for order: {order_id}")


# Create singleton instance
payment_service = RazorpayPaymentService()


async def create_payment_order(
    db: AsyncSession,
    user_id: str,
    plan_id: str,
    amount: float,
    phone_number: str,
    customer_email: str = None
) -> dict:
    """Create payment link and return it."""
    return await payment_service.create_payment_link(
        db=db,
        user_id=user_id,
        plan_id=plan_id,
        amount=Decimal(str(amount)),
        phone_number=phone_number,
        customer_email=customer_email
    )


async def check_payment_status(db: AsyncSession, order_id: str) -> dict:
    """Check payment status."""
    return await payment_service.check_payment_status(db, order_id)


async def handle_payment_webhook(db: AsyncSession, payload: dict, signature: str) -> dict:
    """Handle payment webhook."""
    return await payment_service.handle_webhook(db, payload, signature)


async def verify_razorpay_payment(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str
) -> bool:
    """Verify Razorpay payment signature."""
    return await payment_service.verify_payment(
        razorpay_order_id,
        razorpay_payment_id,
        razorpay_signature
    )