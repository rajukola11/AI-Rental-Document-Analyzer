"""
Broker health-check utilities.

Used by:
  - The /health endpoint to report broker status.
  - _queue_process() to decide whether to queue synchronously or async.
"""
import logging
import time
from functools import lru_cache

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Cache the client — don't create a new connection on every request.
@lru_cache(maxsize=1)
def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(
        settings.celery_broker_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )


def broker_is_healthy(timeout: float = 2.0) -> bool:
    """
    Return True if Redis responds to PING within *timeout* seconds.
    Never raises — failures are logged and returned as False.
    """
    try:
        client = _redis_client()
        return client.ping()
    except Exception as exc:
        logger.warning("Broker health-check failed: %s", exc)
        return False


def wait_for_broker(retries: int = 3, delay: float = 0.5) -> bool:
    """
    Try *retries* times with *delay* seconds between attempts.
    Returns True as soon as broker responds, False if all attempts fail.
    """
    for attempt in range(1, retries + 1):
        if broker_is_healthy():
            return True
        logger.warning("Broker unavailable (attempt %d/%d) — retrying in %.1fs", attempt, retries, delay)
        time.sleep(delay)
    return False
