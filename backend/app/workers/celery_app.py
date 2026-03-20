import os
from pathlib import Path
from celery import Celery

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

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_routes={
        "app.workers.tasks.process_document": {"queue": "documents"},
    },
)