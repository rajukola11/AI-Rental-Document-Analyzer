import uuid
from datetime import datetime
from pydantic import BaseModel


class CheckoutRequest(BaseModel):
    credits: int  # 1, 5, or 10


class CheckoutResponse(BaseModel):
    checkout_url: str
    credits: int
    amount_cents: int


class PaymentResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    credits: int
    amount_cents: int
    currency: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BillingStatus(BaseModel):
    uploads_used: int
    upload_credits: int
    free_uploads_remaining: int
    can_upload: bool
    free_limit: int