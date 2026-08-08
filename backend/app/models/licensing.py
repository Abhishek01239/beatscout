"""Licensing / permission models.

The heart of the rights workflow: a video can only be generated for a
track whose :attr:`Track.rights_status` is ``APPROVED`` (either via an
explicit artist/license-owner permission or a clearly compatible
license — e.g. Creative Commons, public domain, artist upload with
permission).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class License(Base):
    """Confirmed license attached to a track (one per track)."""

    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), unique=True, index=True, nullable=False)

    audio_source: Mapped[str] = mapped_column(String(32), default="artist_upload")
    # artist_upload | permission | creative_commons | public_domain | commercial_provider | other
    license_name: Mapped[str | None] = mapped_column(String(160))       # e.g. "CC BY 4.0"
    license_url: Mapped[str | None] = mapped_column(String(512))
    commercial_use: Mapped[bool] = mapped_column(Boolean, default=False)
    youtube_use: Mapped[bool] = mapped_column(Boolean, default=False)
    modification_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    attribution_required: Mapped[bool] = mapped_column(Boolean, default=False)
    attribution_text: Mapped[str | None] = mapped_column(String(512))   # 'Artist — Track'
    proof_url: Mapped[str | None] = mapped_column(String(512))
    notes: Mapped[dict] = mapped_column(JSON, default=dict)
    verified_by: Mapped[str | None] = mapped_column(String(320))        # email of verifier
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    track = relationship("Track", back_populates="license")


class Permission(Base):
    """Explicit permission record from an artist/license owner."""

    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("track_id", "email", name="uq_perm_track_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    status: Mapped[str] = mapped_column(String(32), default="UNKNOWN", index=True)
    # UNKNOWN | REQUESTED | PENDING | APPROVED | REJECTED | EXPIRED

    artist: Mapped[str] = mapped_column(String(320))
    email: Mapped[str] = mapped_column(String(320))
    permission_text: Mapped[str | None] = mapped_column(String(4000))
    license_type: Mapped[str | None] = mapped_column(String(64))
    commercial_use: Mapped[bool] = mapped_column(Boolean, default=False)
    youtube_use: Mapped[bool] = mapped_column(Boolean, default=False)
    modification_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    attribution_required: Mapped[bool] = mapped_column(Boolean, default=True)
    attribution_text: Mapped[str | None] = mapped_column(String(512))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    proof_url: Mapped[str | None] = mapped_column(String(512))
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)