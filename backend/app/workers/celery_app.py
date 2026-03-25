import os
from pathlib import Path
from celery import Celery
from kombu import Queue, Exchange

_env_file = Path(__file__).resolve().parents[2] / ".env"

if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

broker  = os.environ.get("CELERY_BROKER_URL", "")
backend = os.environ.get("CELERY_RESULT_BACKEND", "")

if not broker:
    raise RuntimeError("CELERY_BROKER_URL is not set in .env")

celery_app = Celery(
    "rental_analyzer",
    broker=broker,
    backend=backend,
    include=["app.workers.tasks"],
)

# ── Queue definitions ─────────────────────────────────────────────────────────
default_exchange   = Exchange("default",   type="direct")
documents_exchange = Exchange("documents", type="direct")

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task reliability
    task_track_started=True,
    task_acks_late=True,                # Only ack after task succeeds — prevents message loss
    task_reject_on_worker_lost=True,    # Re-queue if worker dies mid-task
    worker_prefetch_multiplier=1,       # One task at a time per worker

    # ── Broker connection resilience ──────────────────────────────────────────
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_connection_timeout=10,
    broker_transport_options={
        "visibility_timeout": 3600,     # Redis: re-queue tasks not acked within 1 hour
        "socket_timeout": 10,
        "socket_connect_timeout": 10,
        "socket_keepalive": True,
        "socket_keepalive_options": {},
        "retry_on_timeout": True,
        "health_check_interval": 30,    # Ping broker every 30s to detect stale connections
    },
    broker_pool_limit=10,               # Connection pool — avoids per-task connection overhead

    # ── Result backend ────────────────────────────────────────────────────────
    result_expires=86400,               # Results expire after 24h — avoids backend bloat
    result_backend_transport_options={
        "retry_policy": {"timeout": 5.0}
    },

    # ── Task routing ──────────────────────────────────────────────────────────
    task_queues=(
        Queue("default",   default_exchange,   routing_key="default"),
        Queue("documents", documents_exchange, routing_key="documents"),
    ),
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
    task_routes={
        "app.workers.tasks.process_document":      {"queue": "documents"},
        "app.workers.tasks.reanalyze_document":    {"queue": "documents"},
        "app.workers.tasks.send_deletion_warning": {"queue": "documents"},
        "app.workers.tasks.auto_delete_document":  {"queue": "documents"},
    },

    # ── Worker health ─────────────────────────────────────────────────────────
    worker_max_tasks_per_child=100,     # Recycle worker every 100 tasks — prevents memory leaks
    worker_max_memory_per_child=300_000, # Kill & recycle if worker exceeds 300 MB
)
