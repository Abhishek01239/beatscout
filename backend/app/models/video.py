"""Video models: rendered artifacts + templates."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class VideoTemplate(Base):
    __tablename__ = "video_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)  # minimal | neon | cinematic | spectrum | pulse
    label: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    defaults: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(default=True)


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True, nullable=False)

    template: Mapped[str] = mapped_column(String(64), default="minimal")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    # queued | analyzing | rendering | completed | failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)      # 0..1
    file_path: Mapped[str | None] = mapped_column(Text)              # final MP4
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    width: Mapped[int] = mapped_column(Integer, default=1920)
    height: Mapped[int] = mapped_column(Integer, default=1080)
    fps: Mapped[int] = mapped_column(Integer, default=30)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)       # style overrides
    error: Mapped[str | None] = mapped_column(Text)
    preview: Mapped[bool] = mapped_column(default=False)              # short low-res preview render
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    track = relationship("Track", back_populates="video")