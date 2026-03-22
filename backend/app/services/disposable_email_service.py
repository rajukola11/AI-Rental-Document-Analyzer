"""
Disposable / throwaway email domain blocker.

Fetches the open-source disposable-email-domains list from GitHub on first use
and caches it in memory for the lifetime of the process. This gives us ~50k+
known disposable domains with zero cost and zero per-request latency.

The list is maintained daily at:
  https://github.com/disposable-email-domains/disposable-email-domains
"""

import threading
import urllib.request
from app.core.logging import get_logger

logger = get_logger(__name__)

_BLOCKLIST_URL = (
    "https://raw.githubusercontent.com/disposable-email-domains/"
    "disposable-email-domains/main/disposable_email_blocklist.conf"
)

_lock: threading.Lock = threading.Lock()
_blocked_domains: set[str] | None = None
_load_failed: bool = False


def _load_blocklist() -> set[str]:
    """Fetch and parse the blocklist. Returns empty set on failure."""
    try:
        logger.info("Fetching disposable email blocklist from GitHub…")
        req = urllib.request.Request(
            _BLOCKLIST_URL,
            headers={"User-Agent": "rental-analyzer/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")

        domains = {
            line.strip().lower()
            for line in raw.splitlines()
            if line.strip() and not line.startswith("#")
        }
        logger.info("Loaded %d disposable email domains", len(domains))
        return domains

    except Exception as exc:
        logger.error(
            "Failed to fetch disposable email blocklist: %s — "
            "disposable email blocking will be skipped this session.",
            exc,
        )
        return set()


def _get_blocked_domains() -> set[str]:
    """Lazy-load the blocklist once, thread-safely."""
    global _blocked_domains, _load_failed

    if _blocked_domains is not None:
        return _blocked_domains

    with _lock:
        # Double-checked locking
        if _blocked_domains is not None:
            return _blocked_domains

        _blocked_domains = _load_blocklist()

    return _blocked_domains


def is_disposable_email(email: str) -> bool:
    """
    Return True if the email's domain is on the disposable blocklist.
    Always returns False if the blocklist failed to load (fail open).
    """
    from app.core.config import settings

    if not settings.block_disposable_emails:
        return False

    try:
        domain = email.strip().lower().split("@")[-1]
    except Exception:
        return False

    return domain in _get_blocked_domains()


def preload_blocklist() -> None:
    """
    Call this at app startup (in lifespan) to warm the cache in the background
    so the first registration request doesn't pay the fetch cost.
    """
    thread = threading.Thread(target=_get_blocked_domains, daemon=True, name="disposable-email-loader")
    thread.start()