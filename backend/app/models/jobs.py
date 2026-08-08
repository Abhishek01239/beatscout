"""Job queue + automation models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    job_type: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    # SPOTIFY_DISCOVERY | LICENSE_CHECK | PERMISSION_REQUEST | AUDIO_ANALYSIS
    # | VIDEO_RENDER | THUMBNAIL_RENDER | YOUTUBE_UPLOAD
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", index=True)
    # QUEUED | PROCESSING | COMPLETED | FAILED | CANCELLED
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Automation(Base):
    __tablename__ = "automations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), default="My automation")

    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    discovery_frequency_hours: Mapped[int] = mapped_column(Integer, default=6)
    max_tracks_per_run: Mapped[int] = mapped_column(Integer, default=20)
    max_videos_per_day: Mapped[int] = mapped_column(Integer, default=3)

    auto_permission_request: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_video_generation: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_youtube_upload: Mapped[bool] = mapped_column(Boolean, default=False)

    genres: Mapped[list] = mapped_column(JSON, default=list)
    countries: Mapped[list] = mapped_column(JSON, default=list)
    release_window_days: Mapped[int] = mapped_column(Integer, default=90)
    min_freshness: Mapped[float] = mapped_column(Float, default=0.5)
    max_artist_exposure: Mapped[int] = mapped_column(Integer, default=40)
    max_tracks_per_scan: Mapped[int] = mapped_column(Integer, default=30)

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)