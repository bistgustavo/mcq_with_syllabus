"""Celery application shared by every background worker (ingestion + generation)."""

from celery import Celery

from app.infra import redis_endpoint

_broker = redis_endpoint().url  # cloud Redis if reachable, else local

celery_app = Celery(
    "mcq_platform",
    broker=_broker,
    backend=_broker,
    include=["app.workers.ingestion_worker", "app.workers.generation_worker", "app.workers.research_worker"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_extended=True,
    broker_connection_timeout=3,
    broker_transport_options={"max_retries": 1, "interval_start": 0, "interval_step": 0.5, "interval_max": 1},
    broker_connection_retry_on_startup=True,
)


# --------------------------------------------------------------------------- heartbeat
# Control-channel pings go unanswered while a solo/busy worker runs a long job,
# so each worker also publishes a heartbeat key the health check can read.
HEARTBEAT_KEY = "worker:heartbeat:{hostname}"
HEARTBEAT_TTL = 45


def _start_heartbeat(sender=None, **_kwargs) -> None:
    import os
    import threading
    import time

    hostname = getattr(sender, "hostname", None) or f"worker-{os.getpid()}"

    def beat() -> None:
        from app.redis_client import get_redis

        while True:
            try:
                get_redis().set(HEARTBEAT_KEY.format(hostname=hostname), int(time.time()), ex=HEARTBEAT_TTL)
            except Exception:  # noqa: BLE001 - Redis hiccups must not kill the worker
                pass
            time.sleep(15)

    threading.Thread(target=beat, name="heartbeat", daemon=True).start()


from celery.signals import worker_ready  # noqa: E402

worker_ready.connect(_start_heartbeat)
