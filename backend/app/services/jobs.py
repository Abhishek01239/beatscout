"""Job queue: enqueue + in-process worker (fallback runner).

Two execution modes:
  - **WorkerRunner** — a thread pool executor used by the app when Redis
    is not configured (local dev). Polls ``QUEUED`` jobs and dispatches
    them to the right handler.
  - **Celery** (``app.workers.tasks``) — the production path; workers
    implement the same handlers. ``REDIS_URL`` selects it.

Job types:
    SPOTIFY_DISCOVERY | LICENSE_CHECK | PERMISSION_REQUEST |
    AUDIO_ANALYSIS | VIDEO_RENDER | THUMBNAIL_RENDER | YOUTUBE_UPLOAD
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Job, Track, User, Video, YouTubeUpload

log = logging.getLogger("beatscout.jobs")

JOB_TYPES = {
    "SPOTIFY_DISCOVERY", "LICENSE_CHECK", "PERMISSION_REQUEST",
    "AUDIO_ANALYSIS", "VIDEO_RENDER", "THUMBNAIL_RENDER", "YOUTUBE_UPLOAD",
}

STATUSES = ("QUEUED", "PROCESSING", "COMPLETED", "FAILED", "CANCELLED")


def enqueue(db: Session, *, user_id: int, job_type: str, payload: dict | None = None) -> Job:
    assert job_type in JOB_TYPES, f"unknown job type {job_type}"
    job = Job(user_id=user_id, job_type=job_type,
              status="QUEUED", payload=payload or {}, progress=0.0)
    db.add(job)
    db.commit()
    db.refresh(job)
    log.info("job queued: %s #%d", job_type, job.id)
    return job


# --------------------------- dispatch -------------------------------------

def run_job(job: Job, db: Session) -> None:
    """Execute one job synchronously, updating status/progress."""
    job.status = "PROCESSING"
    job.started_at = now()
    job.attempt += 1
    db.commit()
    try:
        dispatch(job, db)
        job.status = "COMPLETED"
        job.progress = 1.0
    except Exception as exc:
        job.status = "FAILED"
        job.error = f"{type(exc).__name__}: {exc}"
        log.warning("job %s failed: %s", job.id, job.error)
    job.completed_at = now()
    db.commit()


def dispatch(job: Job, db: Session) -> object:
    """Route a job to its handler. Returns handler result (or None)."""
    handlers = {
        "SPOTIFY_DISCOVERY": _h_discovery,
        "LICENSE_CHECK": _h_license_check,
        "PERMISSION_REQUEST": _h_permission_request,
        "AUDIO_ANALYSIS": _h_audio_analysis,
        "VIDEO_RENDER": _h_video_render,
        "THUMBNAIL_RENDER": _h_thumbnail_render,
        "YOUTUBE_UPLOAD": _h_youtube_upload,
    }
    result = handlers[job.job_type](job, db)
    db.flush()
    return result


def _progress(job: Job, db: Session, value: float) -> None:
    job.progress = min(max(value, 0), 1)
    db.commit()


# --------------------------- handlers -------------------------------------

def _h_discovery(job: Job, db: Session) -> dict:
    from ..services.discovery import DiscoveryConfig, discover_and_persist
    cfg = DiscoveryConfig(**job.payload.get("config", {}))
    result = discover_and_persist(db, job.user_id, cfg)
    job.result = result
    return result


def _h_license_check(job: Job, db: Session) -> dict:
    from ..models import Track
    from ..services.rights import require_approved_rights
    track = db.get(Track, job.payload["track_id"])
    require_approved_rights(track)   # raises PermissionError when not APPROVED
    job.result = {"approved": True}
    return job.result


def _h_permission_request(job: Job, db: Session) -> dict:
    from ..models import Track
    from ..services.rights import request_permission
    track = db.get(Track, job.payload["track_id"])
    payload = job.payload
    perm = request_permission(db, track, job.user_id,
                              artist=payload.get("artist"),
                              email=payload["email"],
                              message=payload.get("message"))
    job.result = {"permission_id": perm.id}
    return job.result


def _h_audio_analysis(job: Job, db: Session) -> dict:
    from ..models import AudioSource
    from ..services.audio.analysis import analyze_audio
    audio = db.get(AudioSource, job.payload["audio_source_id"])
    if audio is None:
        raise RuntimeError("audio source not found")
    result = analyze_audio(audio.file_path)
    audio.status = "analysed"
    db.commit()
    job.result = {"bpm": result.get("bpm"), "duration_ms": result.get("duration_ms")}
    return job.result


def _h_video_render(job: Job, db: Session) -> int:
    from ..models import Track
    from ..services.video.service import render_for_track
    track = db.get(Track, job.payload["track_id"]) or db.get(Track, job.payload.get("id"))
    if track is None:
        raise RuntimeError("track not found for video render")
    # The rights gate lives inside render_for_track (require_approved_rights)
    video = render_for_track(
        db, track,
        style=job.payload.get("style", "minimal"),
        settings=job.payload.get("settings", {}),
        as_preview=job.payload.get("preview", False),
    )
    job.result = {"video_id": video.id}
    return video.id


def _h_thumbnail_render(job: Job, db: Session) -> str:
    from ..services.video.thumbnail import render_thumbnail
    from ..config import get_settings
    video = db.get(Video, job.payload["video_id"])
    if video is None or video.track_id is None:
        raise RuntimeError("video not found")
    track = db.get(Track, video.track_id)
    out = Path(get_settings().storage_dir) / "thumbnail" / f"thumb_{video.id}.jpg"
    return render_thumbnail(track, str(out), layout=job.payload.get("layout", "classic"))


def _h_youtube_upload(job: Job, db: Session) -> str:
    from ..services.youtube import upload_video
    upload = db.get(YouTubeUpload, job.payload["upload_id"])
    if upload is None or upload.video_id is None:
        raise RuntimeError("upload record not found")
    video = db.get(Video, upload.video_id)
    if video is None:
        raise RuntimeError("video not found")
    result = upload_video(db, db.get(User, job.user_id), upload, video,
                          title=upload.title, description=upload.description,
                          tags=upload.tags, category=upload.category,
                          privacy=upload.privacy,
                          playlist_id=upload.playlist_id,
                          scheduled_at=upload.scheduled_at)
    job.result = {"youtube_url": result.youtube_url}
    return result.youtube_url


# --------------------------- worker loop ----------------------------------

class LocalWorker:
    """In-process fallback worker: polls QUEUED jobs on a background thread."""

    def __init__(self, poll_seconds: float = 2.0):
        self.poll_seconds = poll_seconds
        self._stop = False
        self._thread = None

    def start(self) -> None:
        import threading
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("local worker started (poll=%.1fs)", self.poll_seconds)

    def stop(self) -> None:
        self._stop = True
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        import time
        while not self._stop:
            try:
                self._tick()
            except Exception:
                log.exception("worker tick error")
            time.sleep(self.poll_seconds)

    def _tick(self) -> None:
        db = SessionLocal()
        try:
            job = (db.query(Job)
                   .filter(Job.status == "QUEUED")
                   .order_by(Job.created_at.asc())
                   .first())
            if job:
                run_job(job, db)
        finally:
            db.close()


def now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)