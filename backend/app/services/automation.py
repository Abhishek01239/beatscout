"""Automation engine: scheduled discovery -> rights gate -> queue jobs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Automation, Track
from .discovery import DiscoveryConfig, discover_and_persist
from .jobs import enqueue
from .rights import require_approved_rights

log = logging.getLogger("beatscout.automation")


def run_automation(db: Session, automation: Automation, user_id: int | None = None) -> dict:
    """Execute one automation pass.

    Pipeline (per automation config):
        discover -> filter emerging -> rights check -> queue approved
    If permission is missing the pipeline STOPS for that track
    (no render / no upload) — enforced by the APPROVED rights gate.
    """
    user_id = user_id or automation.user_id
    cfg = DiscoveryConfig(
        release_window_days=automation.release_window_days,
        genres=automation.genres or [],
        countries=automation.countries or [],
        max_tracks=automation.max_tracks_per_scan or 30,
        min_freshness=automation.min_freshness,
        max_artist_exposure=automation.max_artist_exposure,
    )
    summary = discover_and_persist(db, user_id, cfg)

    candidates = (
        db.query(Track)
        .filter(Track.user_id == user_id)
        .order_by(Track.discovery_score.desc())
        .limit(automation.max_tracks_per_run or 20)
        .all()
    )

    actionable = 0
    jobs_queued = 0
    blocked_no_rights = 0

    for track in candidates:
        # RIGHTS GATE — never auto-render without APPROVED rights
        try:
            require_approved_rights(track)
        except PermissionError:
            blocked_no_rights += 1
            if automation.auto_permission_request and track.rights_status == "UNKNOWN":
                enqueue(db, user_id=user_id, job_type="PERMISSION_REQUEST",
                        payload={"track_id": track.id, "email": "", "message": ""})
            continue

        actionable += 1
        if automation.auto_video_generation and track.video is None:
            enqueue(db, user_id=user_id, job_type="VIDEO_RENDER",
                    payload={"track_id": track.id, "style": "minimal"})
            jobs_queued += 1
        if automation.auto_youtube_upload and track.video and track.video.status == "completed":
            enqueue(db, user_id=user_id, job_type="YOUTUBE_UPLOAD",
                    payload={"video_id": track.video.id})
            jobs_queued += 1

    automation.last_run_at = datetime.now(timezone.utc)
    automation.next_run_at = automation.last_run_at + timedelta(
        hours=automation.discovery_frequency_hours or 6)
    db.commit()

    return {
        "run_id": automation.id,
        **summary,
        "actionable": actionable,
        "jobs_queued": jobs_queued,
        "blocked_no_rights": blocked_no_rights,
        "message": (
            "Run complete. Tracks without verified rights were skipped "
            "(no generation, no upload)."
        ),
    }


def due_automations(db: Session) -> list[Automation]:
    now_dt = datetime.now(timezone.utc)
    return (
        db.query(Automation)
        .filter(Automation.enabled.is_(True))
        .filter((Automation.next_run_at.is_(None)) | (Automation.next_run_at <= now_dt))
        .all()
    )