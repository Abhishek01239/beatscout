"""Automation + job schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .common import ORMModel


class AutomationCreate(BaseModel):
    name: str = "My automation"
    discovery_frequency_hours: int = Field(default=6, ge=1, le=168)
    max_tracks_per_run: int = Field(default=20, ge=1, le=200)
    max_videos_per_day: int = Field(default=3, ge=0, le=100)
    auto_permission_request: bool = False
    auto_video_generation: bool = False
    auto_youtube_upload: bool = False
    genres: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    release_window_days: int = Field(default=90, ge=1, le=3650)
    min_freshness: float = Field(default=0.5, ge=0, le=1)
    max_artist_exposure: int = Field(default=40, ge=0, le=100)
    max_tracks_per_scan: int = Field(default=30, ge=1, le=100)


class AutomationPatch(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    discovery_frequency_hours: int | None = None
    max_tracks_per_run: int | None = None
    max_videos_per_day: int | None = None
    auto_permission_request: bool | None = None
    auto_video_generation: bool | None = None
    auto_youtube_upload: bool | None = None
    genres: list[str] | None = None
    countries: list[str] | None = None
    release_window_days: int | None = None
    min_freshness: float | None = None
    max_artist_exposure: int | None = None
    max_tracks_per_scan: int | None = None


class AutomationOut(ORMModel):
    id: int
    name: str
    enabled: bool
    discovery_frequency_hours: int
    max_tracks_per_run: int
    max_videos_per_day: int
    auto_permission_request: bool
    auto_video_generation: bool
    auto_youtube_upload: bool
    genres: list
    countries: list
    release_window_days: int
    min_freshness: float
    max_artist_exposure: int
    max_tracks_per_scan: int
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime


class AutomationRunResponse(BaseModel):
    run_id: int
    tracks_discovered: int
    candidates: int
    actionable: int
    jobs_queued: int
    blocked_no_rights: int
    message: str


class JobOut(ORMModel):
    id: int
    job_type: str
    status: str
    progress: float
    payload: dict | None = None
    result: dict | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class JobEnqueueRequest(BaseModel):
    job_type: str
    payload: dict = Field(default_factory=dict)