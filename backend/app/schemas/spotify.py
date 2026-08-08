"""Spotify discovery + track schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from .common import ORMModel


class ArtistOut(ORMModel):
    id: int
    name: str
    genres: list[str] = []
    popularity_signal: int | None = None
    country: str | None = None


class TrackOut(ORMModel):
    id: int
    spotify_track_id: str | None = None
    track_name: str
    artist_name: str
    album_name: str | None = None
    release_date: date | None = None
    spotify_url: str | None = None
    album_art_url: str | None = None
    artwork_path: str | None = None
    duration_ms: int | None = None
    genre: str | None = None
    country: str | None = None
    discovery_score: float = 0.0
    exposure_label: str | None = None
    source: str = "spotify"
    status: str = "NEW"
    rights_status: str = "UNKNOWN"
    created_at: datetime


class DiscoverRequest(BaseModel):
    release_window_days: int = Field(default=90, ge=1, le=3650)
    genres: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    max_tracks: int = Field(default=30, ge=1, le=100)
    min_freshness: float = Field(default=0.0, ge=0, le=1)
    max_artist_exposure: int = Field(default=100, ge=0, le=100)
    min_release_date: date | None = None


class DiscoverResult(BaseModel):
    discovered: int
    new_tracks: int
    scoring_summary: dict


class TrackFilter(BaseModel):
    status: str | None = None
    rights_status: str | None = None
    genre: str | None = None
    country: str | None = None
    exposure: str | None = None
    search: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)