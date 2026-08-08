"""Artist / Track models.

Tracks store ONLY metadata from Spotify (id, album, release date, artwork
URL, popularity *signal*) — never audio.  The remote audio file, when
legally obtained, lives in :class:`AudioSource`.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spotify_artist_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    genres: Mapped[list] = mapped_column(JSON, default=list)
    # Optional *signal* of exposure (0=unknown). Intentionally NOT a stream count.
    popularity_signal: Mapped[int | None] = mapped_column(Integer)
    followers_signal: Mapped[int | None] = mapped_column(Integer)
    country: Mapped[str | None] = mapped_column(String(8))
    artwork_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tracks: Mapped[list["Track"]] = relationship(back_populates="artist")


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    spotify_track_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    artist_id: Mapped[int | None] = mapped_column(ForeignKey("artists.id"), index=True)

    track_name: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    artist_name: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    album_name: Mapped[str | None] = mapped_column(String(320))
    release_date: Mapped[date | None] = mapped_column(Date)
    spotify_url: Mapped[str | None] = mapped_column(Text)
    album_art_url: Mapped[str | None] = mapped_column(Text)
    artwork_path: Mapped[str | None] = mapped_column(Text)  # local copy for render
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    external_ids: Mapped[dict] = mapped_column(JSON, default=dict)  # ISRC, EAN, UPC

    # Discovery metadata
    genre: Mapped[str | None] = mapped_column(String(64), index=True)
    country: Mapped[str | None] = mapped_column(String(8))
    discovery_score: Mapped[float] = mapped_column(Float, default=0.0)
    exposure_label: Mapped[str | None] = mapped_column(String(32))  # emerging | small | low_exposure
    source: Mapped[str] = mapped_column(String(32), default="spotify")  # spotify | other
    status: Mapped[str] = mapped_column(String(32), default="NEW", index=True)
    # NEW | PERMISSION_REQUIRED | LICENSED | READY | VIDEO_GENERATED | PUBLISHED
    rights_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN", index=True)
    # UNKNOWN | REQUESTED | PENDING | APPROVED | REJECTED | EXPIRED

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    artist = relationship("Artist", back_populates="tracks", lazy="joined")
    audio_source = relationship("AudioSource", back_populates="track", uselist=False)
    license = relationship("License", back_populates="track", uselist=False)
    video = relationship("Video", back_populates="track", uselist=False)
    uploads = relationship("YouTubeUpload", back_populates="track")


class AudioSource(Base):
    """A legally obtained audio file uploaded by the operator.

    Every file is checksummed (SHA-512), type/format validated and never
    fetched from Spotify.
    """

    __tablename__ = "audio_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(Text)
    format: Mapped[str] = mapped_column(String(16))  # mp3 | wav | flac | m4a
    size_bytes: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    checksum_sha512: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="ready")  # ready | analysing | analysed | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    track = relationship("Track", back_populates="audio_source")