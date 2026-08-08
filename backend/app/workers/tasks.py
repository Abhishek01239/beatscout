"""Celery worker tasks (production path).

Used when REDIS_URL is configured.  The same handlers as the local
worker (:mod:`app.services.jobs`) run here; local dev without Redis
uses the in-process LocalWorker automatically.
"""

from __future__ import annotations

import logging

from ..config import get_settings

log = logging.getLogger("beatscout.workers.tasks")


def make_celery():
    try:
        from celery import Celery
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("celery not installed — pip install celery[redis]") from exc

    settings = get_settings()
    app = Celery(
        "beatscout",
        broker=settings.REDIS_URL,
        backend=settings.REDIS_URL,
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        task_track_started=True,
        broker_connection_retry_on_startup=True,
        worker_max_tasks_per_child=50,
    )

    @app.task(bind=True, name="beatscout.run_job", max_retries=2)
    def run_job(self, job_id: int) -> dict:
        from ..database import SessionLocal
        from ..models import Job
        from ..services.jobs import run_job as execute

        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            if job is None:
                raise RuntimeError(f"job {job_id} not found")
            execute(job, db)
            return {"job_id": job_id, "status": job.status, "error": job.error}
        finally:
            db.close()

    @app.task(name="beatscout.dispatch_queued")
    def dispatch_queued() -> dict:
        """Bulk dispatch all QUEUED jobs (cron-friendly)."""
        from ..database import SessionLocal
        from ..models import Job
        from ..services.jobs import run_job as execute

        db = SessionLocal()
        try:
            jobs = db.query(Job).filter(Job.status == "QUEUED").all()
            for job in jobs:
                execute(job, db)
            return {"dispatched": len(jobs)}
        finally:
            db.close()

    return app


celery_app = make_celery() if get_settings().REDIS_URL else None