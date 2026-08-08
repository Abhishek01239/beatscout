"""Dashboard endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Automation, Job, Track, User, Video, YouTubeUpload
from ..schemas.dashboard import (
    AutomationStatus, DashboardOut, QueueItem, StatCardData,
)
from ..services.spotify import get_spotify_provider
from .deps import get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    uid = current.id
    tracks = db.query(Track).filter(Track.user_id == uid)
    videos = db.query(Video).filter(Video.user_id == uid)
    jobs_q = db.query(Job).filter(Job.user_id == uid)

    queue = [
        QueueItem(id=job.id, job_type=job.job_type, status=job.status,
                  progress=job.progress, created_at=job.created_at)
        for job in jobs_q.filter(Job.status.in_(("QUEUED", "PROCESSING")))
        .order_by(Job.created_at.asc()).limit(8).all()
    ]

    automations = db.query(Automation).filter(Automation.user_id == uid).all()
    enabled = [a for a in automations if a.enabled]
    next_runs = [a.next_run_at for a in enabled if a.next_run_at]
    frequencies = [a.discovery_frequency_hours for a in enabled if a.discovery_frequency_hours]

    return DashboardOut(
        stats=StatCardData(
            tracks_discovered=tracks.count(),
            awaiting_permission=tracks.filter(Track.rights_status == "REQUESTED").count(),
            licensed_tracks=tracks.filter(Track.rights_status == "APPROVED").count(),
            videos_generated=videos.filter(Video.status == "completed").count(),
            uploaded_to_youtube=db.query(YouTubeUpload).filter(
                YouTubeUpload.user_id == uid,
                YouTubeUpload.status.in_(("uploaded", "published", "scheduled")),
            ).count(),
            failed_jobs=jobs_q.filter(Job.status == "FAILED").count(),
        ),
        recent_tracks=tracks.order_by(Track.created_at.desc()).limit(5).all(),
        recent_videos=videos.order_by(Video.created_at.desc()).limit(5).all(),
        recent_uploads=(db.query(YouTubeUpload).filter(YouTubeUpload.user_id == uid)
                        .order_by(YouTubeUpload.created_at.desc()).limit(5).all()),
        queue=queue,
        automation=AutomationStatus(
            automation_count=len(automations),
            enabled=len(enabled),
            next_run_at=min(next_runs) if next_runs else None,
            discovery_frequency_hours=min(frequencies) if frequencies else None,
        ),
        provider_mode=get_spotify_provider().name,
    )