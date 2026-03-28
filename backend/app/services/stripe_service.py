import stripe
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

CURRENCY = "eur"

# ── Credit packages ───────────────────────────────────────────────────────────
# bonus_credits are added on the FIRST purchase only (handled in webhook)
CREDIT_PACKAGES = [
    {
        "credits": 1,
        "amount_cents": 100,
        "label": "Pay-As-You-Go — €1 per analysis",
        "bonus_credits": 0,
        "popular": False,
        "best_value": False,
    },
    {
        "credits": 6,
        "amount_cents": 400,
        "label": "6 analyses — €4 (save 43%)",
        "bonus_credits": 1,          # +1 on first purchase → 7 total
        "popular": True,
        "best_value": False,
    },
    {
        "credits": 20,
        "amount_cents": 1000,
        "label": "20 analyses — €10 (save 57%)",
        "bonus_credits": 3,          # +3 on first purchase → 23 total
        "popular": False,
        "best_value": True,
    },
]


def _init():
    stripe.api_key = settings.stripe_secret_key


def create_checkout_session(
    user_id: str,
    user_email: str,
    credits: int,
    amount_cents: int,
    success_url: str,
    cancel_url: str,
) -> str:
    _init()
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        customer_email=user_email,
        line_items=[{
            "price_data": {
                "currency": CURRENCY,
                "unit_amount": amount_cents,
                "product_data": {
                    "name": f"Rental Analyzer — {credits} document {'analysis' if credits == 1 else 'analyses'}",
                    "description": "AI-powered German rental contract analysis",
                },
            },
            "quantity": 1,
        }],
        metadata={
            "user_id": user_id,
            "credits": str(credits),
        },
        success_url=success_url,
        cancel_url=cancel_url,
    )
    logger.info("Stripe session created", extra={"session_id": session.id, "user_id": user_id})
    return session.url


def construct_webhook_event(payload: bytes, sig_header: str):
    _init()
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )