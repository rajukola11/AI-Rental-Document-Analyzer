"""
Pytest test suite for app/services/stripe_service.py

Covers:
- CREDIT_PACKAGES constants    : structure, required fields, business rules
- CURRENCY constant            : value is "eur"
- _init                        : sets stripe.api_key from settings
- create_checkout_session      : returns session URL, correct stripe.Session.create
                                 arguments (line items, metadata, URLs, email,
                                 payment mode), singular/plural product name,
                                 StripeError propagates
- construct_webhook_event      : delegates to stripe.Webhook.construct_event,
                                 passes payload + sig + secret correctly,
                                 SignatureVerificationError propagates,
                                 AuthenticationError propagates

No real Stripe API calls — stripe SDK is always mocked.
Settings are stubbed via tests/conftest.py.
"""

import pytest
from unittest.mock import MagicMock, patch, call
import stripe

from app.services.stripe_service import (
    CURRENCY,
    CREDIT_PACKAGES,
    _init,
    create_checkout_session,
    construct_webhook_event,
)


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _fake_session(url: str = "https://checkout.stripe.com/pay/cs_test_abc") -> MagicMock:
    sess = MagicMock()
    sess.id = "cs_test_abc123"
    sess.url = url
    return sess


def _patch_session_create(return_value=None, side_effect=None):
    mock_sess = return_value or _fake_session()
    return patch(
        "stripe.checkout.Session.create",
        return_value=mock_sess if side_effect is None else None,
        side_effect=side_effect,
    )


# ===========================================================================
# CURRENCY constant
# ===========================================================================

class TestCurrencyConstant:
    def test_currency_is_eur(self):
        assert CURRENCY == "eur"

    def test_currency_is_lowercase(self):
        assert CURRENCY == CURRENCY.lower()


# ===========================================================================
# CREDIT_PACKAGES constant
# ===========================================================================

class TestCreditPackages:
    def test_is_a_list(self):
        assert isinstance(CREDIT_PACKAGES, list)

    def test_has_three_packages(self):
        assert len(CREDIT_PACKAGES) == 3

    def test_every_package_has_required_keys(self):
        required = {"credits", "amount_cents", "label", "bonus_credits", "popular", "best_value"}
        for pkg in CREDIT_PACKAGES:
            missing = required - pkg.keys()
            assert not missing, f"Package missing keys: {missing}"

    def test_credits_are_positive_integers(self):
        for pkg in CREDIT_PACKAGES:
            assert isinstance(pkg["credits"], int)
            assert pkg["credits"] > 0

    def test_amount_cents_are_positive(self):
        for pkg in CREDIT_PACKAGES:
            assert isinstance(pkg["amount_cents"], int)
            assert pkg["amount_cents"] > 0

    def test_bonus_credits_are_non_negative(self):
        for pkg in CREDIT_PACKAGES:
            assert isinstance(pkg["bonus_credits"], int)
            assert pkg["bonus_credits"] >= 0

    def test_popular_and_best_value_are_bools(self):
        for pkg in CREDIT_PACKAGES:
            assert isinstance(pkg["popular"], bool)
            assert isinstance(pkg["best_value"], bool)

    def test_label_is_non_empty_string(self):
        for pkg in CREDIT_PACKAGES:
            assert isinstance(pkg["label"], str)
            assert len(pkg["label"]) > 0

    def test_exactly_one_popular_package(self):
        popular = [p for p in CREDIT_PACKAGES if p["popular"]]
        assert len(popular) == 1

    def test_exactly_one_best_value_package(self):
        best = [p for p in CREDIT_PACKAGES if p["best_value"]]
        assert len(best) == 1

    def test_no_package_is_both_popular_and_best_value(self):
        both = [p for p in CREDIT_PACKAGES if p["popular"] and p["best_value"]]
        assert len(both) == 0

    def test_packages_sorted_by_price_ascending(self):
        amounts = [p["amount_cents"] for p in CREDIT_PACKAGES]
        assert amounts == sorted(amounts)

    def test_first_package_has_no_bonus_credits(self):
        assert CREDIT_PACKAGES[0]["bonus_credits"] == 0

    def test_bulk_packages_have_bonus_credits(self):
        for pkg in CREDIT_PACKAGES[1:]:
            assert pkg["bonus_credits"] > 0

    def test_credit_counts_are_unique(self):
        counts = [p["credits"] for p in CREDIT_PACKAGES]
        assert len(counts) == len(set(counts))


# ===========================================================================
# _init
# ===========================================================================

class TestInit:
    def test_sets_stripe_api_key(self):
        _init()
        assert stripe.api_key == "sk_test_fake"

    def test_uses_value_from_settings(self):
        import app.core.config as _cfg
        original = _cfg.settings.stripe_secret_key
        _cfg.settings.stripe_secret_key = "sk_live_different"
        try:
            _init()
            assert stripe.api_key == "sk_live_different"
        finally:
            _cfg.settings.stripe_secret_key = original


# ===========================================================================
# create_checkout_session
# ===========================================================================

SESSION_URL = "https://checkout.stripe.com/pay/cs_test_xyz"

# Standard call args used across most tests
_CALL_KWARGS = dict(
    user_id="user-uuid-123",
    user_email="tenant@example.com",
    credits=6,
    amount_cents=400,
    success_url="https://app.example.com/billing?success=true",
    cancel_url="https://app.example.com/billing?cancel=true",
)


class TestCreateCheckoutSession:

    # ── Return value ──────────────────────────────────────────────────────────

    def test_returns_string(self):
        with _patch_session_create(_fake_session(SESSION_URL)):
            result = create_checkout_session(**_CALL_KWARGS)
        assert isinstance(result, str)

    def test_returns_session_url(self):
        with _patch_session_create(_fake_session(SESSION_URL)):
            result = create_checkout_session(**_CALL_KWARGS)
        assert result == SESSION_URL

    # ── stripe.checkout.Session.create arguments ──────────────────────────────

    def test_payment_method_types_is_card(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**_CALL_KWARGS)
        kwargs = mock_create.call_args.kwargs
        assert kwargs["payment_method_types"] == ["card"]

    def test_mode_is_payment(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**_CALL_KWARGS)
        kwargs = mock_create.call_args.kwargs
        assert kwargs["mode"] == "payment"

    def test_customer_email_passed(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**_CALL_KWARGS)
        kwargs = mock_create.call_args.kwargs
        assert kwargs["customer_email"] == "tenant@example.com"

    def test_success_url_passed(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**_CALL_KWARGS)
        kwargs = mock_create.call_args.kwargs
        assert kwargs["success_url"] == "https://app.example.com/billing?success=true"

    def test_cancel_url_passed(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**_CALL_KWARGS)
        kwargs = mock_create.call_args.kwargs
        assert kwargs["cancel_url"] == "https://app.example.com/billing?cancel=true"

    # ── line_items ────────────────────────────────────────────────────────────

    def test_line_items_has_one_entry(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**_CALL_KWARGS)
        line_items = mock_create.call_args.kwargs["line_items"]
        assert len(line_items) == 1

    def test_line_item_quantity_is_one(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**_CALL_KWARGS)
        item = mock_create.call_args.kwargs["line_items"][0]
        assert item["quantity"] == 1

    def test_line_item_currency_is_eur(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**_CALL_KWARGS)
        price_data = mock_create.call_args.kwargs["line_items"][0]["price_data"]
        assert price_data["currency"] == "eur"

    def test_line_item_amount_cents_correct(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**_CALL_KWARGS)
        price_data = mock_create.call_args.kwargs["line_items"][0]["price_data"]
        assert price_data["unit_amount"] == 400

    def test_product_name_uses_plural_for_multiple_credits(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**{**_CALL_KWARGS, "credits": 6})
        product = mock_create.call_args.kwargs["line_items"][0]["price_data"]["product_data"]
        assert "analyses" in product["name"]

    def test_product_name_uses_singular_for_one_credit(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**{**_CALL_KWARGS, "credits": 1, "amount_cents": 100})
        product = mock_create.call_args.kwargs["line_items"][0]["price_data"]["product_data"]
        assert "analysis" in product["name"]
        assert "analyses" not in product["name"]

    def test_product_description_mentions_german(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**_CALL_KWARGS)
        product = mock_create.call_args.kwargs["line_items"][0]["price_data"]["product_data"]
        assert "German" in product["description"] or "rental" in product["description"].lower()

    # ── metadata ─────────────────────────────────────────────────────────────

    def test_metadata_contains_user_id(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**_CALL_KWARGS)
        metadata = mock_create.call_args.kwargs["metadata"]
        assert metadata["user_id"] == "user-uuid-123"

    def test_metadata_contains_credits_as_string(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**_CALL_KWARGS)
        metadata = mock_create.call_args.kwargs["metadata"]
        assert metadata["credits"] == "6"
        assert isinstance(metadata["credits"], str)

    def test_metadata_credits_matches_argument(self):
        with _patch_session_create() as mock_create:
            create_checkout_session(**{**_CALL_KWARGS, "credits": 20})
        metadata = mock_create.call_args.kwargs["metadata"]
        assert metadata["credits"] == "20"

    # ── Error handling ────────────────────────────────────────────────────────

    def test_stripe_error_propagates(self):
        err = stripe.error.StripeError("stripe is down")
        with _patch_session_create(side_effect=err):
            with pytest.raises(stripe.error.StripeError):
                create_checkout_session(**_CALL_KWARGS)

    def test_authentication_error_propagates(self):
        err = stripe.error.AuthenticationError("bad api key")
        with _patch_session_create(side_effect=err):
            with pytest.raises(stripe.error.AuthenticationError):
                create_checkout_session(**_CALL_KWARGS)

    def test_invalid_request_error_propagates(self):
        err = stripe.error.InvalidRequestError("invalid params", "param")
        with _patch_session_create(side_effect=err):
            with pytest.raises(stripe.error.InvalidRequestError):
                create_checkout_session(**_CALL_KWARGS)


# ===========================================================================
# construct_webhook_event
# ===========================================================================

FAKE_PAYLOAD = b'{"type":"checkout.session.completed","data":{}}'
FAKE_SIG     = "t=1234,v1=abcdef"


class TestConstructWebhookEvent:
    def test_returns_result_of_construct_event(self):
        fake_event = {"type": "checkout.session.completed", "data": {}}
        with patch("stripe.Webhook.construct_event", return_value=fake_event) as mock_ce:
            result = construct_webhook_event(FAKE_PAYLOAD, FAKE_SIG)
        assert result == fake_event

    def test_passes_payload_to_construct_event(self):
        with patch("stripe.Webhook.construct_event", return_value={}) as mock_ce:
            construct_webhook_event(FAKE_PAYLOAD, FAKE_SIG)
        args = mock_ce.call_args.args
        assert args[0] == FAKE_PAYLOAD

    def test_passes_sig_header_to_construct_event(self):
        with patch("stripe.Webhook.construct_event", return_value={}) as mock_ce:
            construct_webhook_event(FAKE_PAYLOAD, FAKE_SIG)
        args = mock_ce.call_args.args
        assert args[1] == FAKE_SIG

    def test_passes_webhook_secret_from_settings(self):
        with patch("stripe.Webhook.construct_event", return_value={}) as mock_ce:
            construct_webhook_event(FAKE_PAYLOAD, FAKE_SIG)
        args = mock_ce.call_args.args
        assert args[2] == "whsec_fake"

    def test_signature_verification_error_propagates(self):
        err = stripe.error.SignatureVerificationError("bad sig", FAKE_SIG)
        with patch("stripe.Webhook.construct_event", side_effect=err):
            with pytest.raises(stripe.error.SignatureVerificationError):
                construct_webhook_event(FAKE_PAYLOAD, "bad-sig-header")

    def test_stripe_error_propagates(self):
        err = stripe.error.StripeError("generic stripe error")
        with patch("stripe.Webhook.construct_event", side_effect=err):
            with pytest.raises(stripe.error.StripeError):
                construct_webhook_event(FAKE_PAYLOAD, FAKE_SIG)

    def test_construct_event_called_once(self):
        with patch("stripe.Webhook.construct_event", return_value={}) as mock_ce:
            construct_webhook_event(FAKE_PAYLOAD, FAKE_SIG)
        mock_ce.assert_called_once()

    def test_sets_api_key_before_call(self):
        """_init() must be called first, so api_key is set on every webhook verify."""
        with patch("stripe.Webhook.construct_event", return_value={}):
            construct_webhook_event(FAKE_PAYLOAD, FAKE_SIG)
        assert stripe.api_key == "sk_test_fake"