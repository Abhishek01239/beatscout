"""Spotify provider protocol + shared discovery primitives.

BeatScout uses Spotify strictly as a *discovery/metadata* source:

- track/artist/album metadata, artwork URL, release date, duration
- popularity is stored as a coarse "popularity signal", NEVER presented
  as an exact stream count.

Spotify audio is NEVER downloaded, ripped or captured. Video generation
requires a separately uploaded, legally obtained audio file
(see `app.services.licensing`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class SpotifyTrackMeta:
    """Normalized track metadata returned by any provider (REAL or MOCK)."""
    spotify_track_id: str
    spotify_artist_id: str
    track_name: str
    artist_name: str
    album_name: str | None = None
    release_date: date | None = None
    spotify_url: str = ""
    album_art_url: str = ""
    duration_ms: int | None = None
    popularity_signal: int = 0        # 0-100 Spotify popularity score (signal)
    artist_popularity_signal: int = 0
    artist_followers_signal: int | None = None
    genres: list[str] = field(default_factory=list)
    country: str | None = None
    external_ids: dict = field(default_factory=dict)
    isrc: str | None = None


class SpotifyProviderBase:
    """Interface implemented by both the mock and the real client."""

    provider_name: str = "base"   # "REAL" | "MOCK"

    def search(self, query: str, limit: int = 20) -> list[SpotifyTrackMeta]:
        raise NotImplementedError

    def discover(self, *, genres: list[str], release_from: date,
                 release_to: date, limit: int = 30, country: str | None = None) -> list[SpotifyTrackMeta]:
        raise NotImplementedError

    def get_track(self, spotify_track_id: str) -> SpotifyTrackMeta | None:
        raise NotImplementedError

    def rate_limit_message(self) -> str:
        return "Spotify API rate limit exceeded. Retry later."