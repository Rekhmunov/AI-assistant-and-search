from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery = Celery(
    "aisearch",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    imports=["app.workers.broadcast_tasks"],
)
