"""
Email service backed by Resend (https://resend.com).

If RESEND_API_KEY is empty (local dev), emails are logged to console instead
of being sent — no config required for development.
"""

import json
import urllib.request
import urllib.error
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"


def _send_via_resend(to: str, subject: str, html: str) -> None:
    payload = json.dumps({
        "from": settings.email_from,
        "to": [to],
        "subject": subject,
        "html": html,
    }).encode("utf-8")

    req = urllib.request.Request(
        _RESEND_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info("Email sent via Resend to %s (status %s)", to, resp.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.error("Resend API error %s: %s", exc.code, body)
        raise RuntimeError(f"Failed to send email via Resend: {exc.code} {body}") from exc


def _send_to_console(to: str, subject: str, html: str) -> None:
    """Dev fallback — print the email so developers can grab the link."""
    import re
    # Strip tags for readable console output
    plain = re.sub(r"<[^>]+>", "", html).strip()
    logger.info(
        "\n" + "─" * 60 +
        f"\n📧  DEV EMAIL (not sent — set RESEND_API_KEY to send)\n"
        f"To:      {to}\n"
        f"Subject: {subject}\n\n"
        f"{plain}\n" +
        "─" * 60
    )


def send_email(to: str, subject: str, html: str) -> None:
    """
    Send an email. Uses Resend in production, console in dev.
    Errors are logged but NOT re-raised — a failed email should never
    crash registration or break the request cycle.
    """
    print("🚨 RESEND KEY DEBUG:", settings.resend_api_key)
    try:
        if settings.resend_api_key:
            _send_via_resend(to, subject, html)
        else:
            _send_to_console(to, subject, html)
    except Exception as exc:
        logger.error("Email send failed to %s: %s", to, exc)


# ── Email templates ───────────────────────────────────────────────────────────

def send_verification_email(to: str, full_name: str | None, token: str) -> None:
    verify_url = f"{settings.frontend_url}/verify-email?token={token}"
    name = full_name or "there"

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: sans-serif; max-width: 560px; margin: 0 auto; padding: 32px; color: #111;">
      <h2 style="margin-bottom: 8px;">Verify your email address</h2>
      <p>Hi {name},</p>
      <p>Thanks for signing up for <strong>Rental Document Analyzer</strong>.
         Please confirm your email address to activate your account.</p>
      <p style="margin: 32px 0;">
        <a href="{verify_url}"
           style="background: #2563EB; color: #fff; padding: 12px 24px;
                  border-radius: 6px; text-decoration: none; font-weight: 600;">
          Verify my email
        </a>
      </p>
      <p style="color: #666; font-size: 14px;">
        This link expires in {settings.verification_token_expire_hours} hours.
        If you didn't create an account, you can safely ignore this email.
      </p>
      <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
      <p style="color: #999; font-size: 12px;">
        Can't click the button? Copy this link:<br/>
        <a href="{verify_url}" style="color: #2563EB;">{verify_url}</a>
      </p>
    </body>
    </html>
    """
    send_email(to, "Verify your email — Rental Document Analyzer", html)


def send_welcome_email(to: str, full_name: str | None) -> None:
    name = full_name or "there"
    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: sans-serif; max-width: 560px; margin: 0 auto; padding: 32px; color: #111;">
      <h2>Welcome to Rental Document Analyzer 🏠</h2>
      <p>Hi {name},</p>
      <p>Your email is verified. You're all set — you have
         <strong>2 free analyses</strong> to get started.</p>
      <p>Upload your first rental contract and we'll analyze every clause,
         flag the risks, and explain everything in plain English.</p>
      <p style="margin: 32px 0;">
        <a href="{settings.frontend_url}/upload"
           style="background: #2563EB; color: #fff; padding: 12px 24px;
                  border-radius: 6px; text-decoration: none; font-weight: 600;">
          Upload a contract
        </a>
      </p>
    </body>
    </html>
    """
    send_email(to, "Welcome to Rental Document Analyzer!", html)