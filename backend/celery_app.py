from celery import Celery
from celery.schedules import crontab

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
    imports=["app.workers.broadcast_tasks", "app.workers.maintenance_tasks", "app.workers.agent_tasks"],
    beat_schedule={
        "dispatch-agent-reminders": {
            "task": "dispatch_agent_reminders",
            "schedule": crontab(minute="*"),
        },
        "purge-agent-activity-logs": {
            "task": "purge_agent_activity_logs",
            "schedule": crontab(minute=5, hour="*"),
        },
        "cleanup-expired-uploads": {
            "task": "cleanup_expired_uploads",
            "schedule": crontab(minute=15, hour="*/6"),
        },
        "reconcile-orphan-uploads": {
            "task": "reconcile_orphan_uploads",
            "schedule": crontab(hour=5, minute=30, day_of_week=0),
        },
        "purge-deleted-accounts": {
            "task": "purge_deleted_accounts",
            "schedule": crontab(hour=4, minute=45),
        },
        "dispatch-poster-scheduled": {
            "task": "dispatch_poster_scheduled",
            "schedule": crontab(minute="*/5"),  # каждые 5 минут
        },
        "publish-scheduled-blog-posts": {
            "task": "publish_scheduled_blog_posts",
            "schedule": crontab(minute="*/5"),  # каждые 5 минут
        },
    },
)
