"""External account + YouTube upload models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class SpotifyAccount(Base):
    """Unified-ish record of the Spotify connection (not used for audio)."""

    __tablename__ = "spotify_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    spotify_user_id: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(160))
    access_token: Mapped[str | None] = mapped_column(Text)  # encrypted at rest via SECRET_KEY
    refresh_token: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default="disconnected")  # connected | disconnected | error
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="spotify_account")


class YouTubeAccount(Base):
    __tablename__ = "youtube_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    channel_id: Mapped[str | None] = mapped_column(String(64))
    channel_name: Mapped[str | None] = mapped_column(String(320))
    subscriber_count: Mapped[int | None] = mapped_column(Integer)
    video_count: Mapped[int | None] = mapped_column(Integer)
    access_token: Mapped[str | None] = mapped_column(Text)   # encrypted
    refresh_token: Mapped[str | None] = mapped_column(Text)  # encrypted
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default="disconnected")  # connected | disconnected | error
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="youtube_account")


class YouTubeUpload(Base):
    __tablename__ = "youtube_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True, nullable=False)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), index=True, nullable=False)

    youtube_video_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(32), default="music")
    privacy: Mapped[str] = mapped_column(String(16), default="private")  # public|unlisted|private|scheduled
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    playlist_id: Mapped[str | None] = mapped_column(String(64))
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    # draft | uploading | uploaded | published | scheduled | failed
    youtube_url: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    track = relationship("Track", back_populates="uploads")
    video = relationship("Video")