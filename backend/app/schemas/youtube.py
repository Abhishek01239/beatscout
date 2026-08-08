"""YouTube schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .common import ORMModel


class YouTubeChannelOut(ORMModel):
    channel_id: str | None = None
    channel_name: str | None = None
    subscriber_count: int | None = None
    video_count: int | None = None
    status: str
    created_at: datetime | None = None


class UploadRequest(BaseModel):
    video_id: int
    title: str = Field(default="", max_length=200, description="empty => auto-generate from track")
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    category: str = "music"  # music | entertainment | education ...
    privacy: str = Field(default="private", pattern="^(public|unlisted|private|scheduled)$")
    scheduled_at: datetime | None = None
    playlist_id: str | None = None
    thumbnail_path: str | None = None


class YouTubeUploadOut(ORMModel):
    id: int
    track_id: int
    video_id: int
    title: str
    description: str
    privacy: str
    status: str
    youtube_url: str | None = None
    youtube_video_id: str | None = None
    error: str | None = None
    scheduled_at: datetime | None = None
    created_at: datetime


class MetadataPreview(BaseModel):
    title: str
    description: str
    tags: list[str]
    attribution: str | None = None
    disclaimers: list[str]