"""Dashboard aggregate schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .spotify import TrackOut
from .video import VideoOut
from .youtube import YouTubeUploadOut


class StatCardData(BaseModel):
    tracks_discovered: int
    awaiting_permission: int
    licensed_tracks: int
    videos_generated: int
    uploaded_to_youtube: int
    failed_jobs: int


class QueueItem(BaseModel):
    id: int
    job_type: str
    status: str
    progress: float
    created_at: datetime


class AutomationStatus(BaseModel):
    automation_count: int
    enabled: int
    next_run_at: datetime | None = None
    discovery_frequency_hours: int | None = None


class DashboardOut(BaseModel):
    stats: StatCardData
    recent_tracks: list[TrackOut]
    recent_videos: list[VideoOut]
    recent_uploads: list[YouTubeUploadOut]
    queue: list[QueueItem]
    automation: AutomationStatus
    provider_mode: str