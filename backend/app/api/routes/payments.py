import uuid
from fastapi import APIRouter, Header, HTTPException, Request, status
from app.core.config import settings
from app.core.dependencies import CurrentUser, DBSession
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.models.payment import Payment
from app.models.user import FREE_UPLOAD_LIMIT
from app.schemas.payment import (
    BillingStatus, CheckoutRequest, CheckoutResponse, PaymentResponse
)
from app.services.stripe_service import (
    CREDIT_PACKAGES, construct_webhook_event, create_checkout_session
)

router = APIRouter()
logger = get_logger(__name__)


# ── Billing status ────────────────────────────────────────────────────────────

@router.get("/billing", response_model=BillingStatus, summary="Get current billing status")
def get_billing(payload: CurrentUser, db: DBSession):
    from app.models.user import User
    user = db.query(User).filter(User.id == uuid.UUID(payload["sub"])).first()
    return BillingStatus(
        uploads_used=user.uploads_used,
        upload_credits=user.upload_credits,
        free_uploads_remaining=user.free_uploads_remaining,
        can_upload=user.can_upload,
        free_limit=FREE_UPLOAD_LIMIT,
    )


# ── Packages list ─────────────────────────────────────────────────────────────

@router.get("/packages", summary="List available credit packages")
def list_packages():
    return {"packages": CREDIT_PACKAGES}


# ── Create checkout session ───────────────────────────────────────────────────

@router.post("/checkout", response_model=CheckoutResponse, summary="Create Stripe checkout session")
def create_checkout(body: CheckoutRequest, payload: CurrentUser, db: DBSession):
    # Find matching package
    pkg = next((p for p in CREDIT_PACKAGES if p["credits"] == body.credits), None)
    if not pkg:
        raise ValidationError(f"Invalid credit amount. Choose from: {[p['credits'] for p in CREDIT_PACKAGES]}")

    from app.models.user import User
    user = db.query(User).filter(User.id == uuid.UUID(payload["sub"])).first()

    frontend = settings.allowed_origins.split(",")[0].strip()
    checkout_url = create_checkout_session(
        user_id=str(user.id),
        user_email=user.email,
        credits=pkg["credits"],
        amount_cents=pkg["amount_cents"],
        success_url=f"{frontend}/billing?success=true",
        cancel_url=f"{frontend}/billing?cancelled=true",
    )

    # Create pending payment record
    payment = Payment(
        user_id=user.id,
        stripe_session_id="pending",  # updated by webhook
        amount_cents=pkg["amount_cents"],
        currency="eur",
        credits=pkg["credits"],
        status="pending",
    )
    db.add(payment)
    db.flush()

    return CheckoutResponse(
        checkout_url=checkout_url,
        credits=pkg["credits"],
        amount_cents=pkg["amount_cents"],
    )


# ── Stripe webhook ────────────────────────────────────────────────────────────

@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: DBSession, stripe_signature: str = Header(None)):
    """
    Stripe sends events here after payment.
    Verifies signature, then grants credits to user.
    """
    payload = await request.body()

    try:
        event = construct_webhook_event(payload, stripe_signature)
    except Exception as exc:
        logger.error("Webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session["metadata"]["user_id"]
        credits = int(session["metadata"]["credits"])
        session_id = session["id"]
        payment_intent = session.get("payment_intent")

        from app.models.user import User

        # Grant credits to user
        user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
        if user:
            user.upload_credits += credits

        # Record payment
        payment = Payment(
            user_id=uuid.UUID(user_id),
            stripe_session_id=session_id,
            stripe_payment_intent=payment_intent,
            amount_cents=session["amount_total"],
            currency=session["currency"],
            credits=credits,
            status="completed",
        )
        db.add(payment)
        db.flush()

        logger.info(
            "Payment completed",
            extra={"user_id": user_id, "credits": credits, "session_id": session_id},
        )

    elif event["type"] in ("payment_intent.payment_failed", "checkout.session.expired"):
        session = event["data"]["object"]
        session_id = session.get("id", "")
        payment = db.query(Payment).filter(Payment.stripe_session_id == session_id).first()
        if payment:
            payment.status = "failed"
        logger.warning("Payment failed/expired", extra={"session_id": session_id})

    return {"received": True}


# ── Payment history ───────────────────────────────────────────────────────────

@router.get("/history", response_model=list[PaymentResponse], summary="User payment history")
def payment_history(payload: CurrentUser, db: DBSession):
    user_id = uuid.UUID(payload["sub"])
    return (
        db.query(Payment)
        .filter(Payment.user_id == user_id, Payment.status == "completed")
        .order_by(Payment.created_at.desc())
        .all()
    )