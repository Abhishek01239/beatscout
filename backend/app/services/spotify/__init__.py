"""Spotify provider factory + discovery scoring engine."""

from __future__ import annotations

from datetime import date

from ...config import get_settings
from .base import SpotifyProviderBase, SpotifyTrackMeta
from .mock import MockSpotifyProvider
from .real import RealSpotifyProvider

GENRES = [
    "Electronic", "Hip-Hop", "Lo-fi", "Ambient", "Pop", "Rock",
    "Indie", "EDM", "Experimental", "Folk", "Custom",
]


def get_spotify_provider() -> SpotifyProviderBase:
    settings = get_settings()
    if settings.has_spotify_credentials:
        try:
            return RealSpotifyProvider()
        except Exception:
            # If credentials are stale/unusable, degrade to mock instead of crashing
            return MockSpotifyProvider()
    return MockSpotifyProvider()


# ---------------------------------------------------------------------------
# Scoring — the "Low exposure candidate" heuristic.
# This intentionally does NOT claim stream counts. It is a configurable
# quality/recency signal used to prioritize reviewable candidates.
# ---------------------------------------------------------------------------

FRESHNESS_DAYS = {7: 1.0, 30: 0.85, 90: 0.65, 180: 0.45, 365: 0.25}


def freshness_score(release_date: date | None, max_days: int = 365) -> float:
    """1.0 for brand-new, decaying linearly to 0 at `max_days` old."""
    if release_date is None:
        return 0.5
    age_days = max(0, (date.today() - release_date).days)
    if age_days == 0:
        return 1.0
    return max(0.0, 1.0 - age_days / max_days)


def emerging_score(popularity_signal: int, followers_signal: int | None = None) -> float:
    """Small popularity signal -> emerging. 0-100 signal mapped 1..0."""
    pop = min(max(popularity_signal, 0), 100)
    score = 1.0 - pop / 100.0
    if followers_signal is not None:
        score = score * 0.7 + (0.3 if followers_signal < 5000 else 0.1)
    return round(min(max(score, 0.0), 1.0), 3)


def genre_match_score(track_genres: list[str], wanted: list[str]) -> float:
    if not wanted or not track_genres:
        return 0.5
    return 1.0 if set(track_genres) & set(wanted) else 0.0


def artist_size_score(followers_signal: int | None, popularity_signal: int) -> float:
    """Small artist -> higher score (preferred for discovery)."""
    if followers_signal is None:
        return 1.0 - popularity_signal / 100.0
    if followers_signal < 1000:
        return 1.0
    if followers_signal < 5000:
        return 0.7
    if followers_signal < 20000:
        return 0.4
    return 0.15


def discovery_score(meta: SpotifyTrackMeta, wanted_genres: list[str]) -> float:
    """Composed candidate score (see README §Discovery)."""
    return round(
        freshness_score(meta.release_date) * 40.0
        + emerging_score(meta.popularity_signal, meta.artist_followers_signal) * 30.0
        + genre_match_score(meta.genres, wanted_genres) * 15.0
        + artist_size_score(meta.artist_followers_signal, meta.popularity_signal) * 15.0,
        2,
    )


def exposure_label(meta: SpotifyTrackMeta) -> str:
    """Human exposure bucket — deliberately NOT a stream count."""
    pop = meta.popularity_signal
    followers = meta.artist_followers_signal
    if pop <= 10 or (followers is not None and followers < 500):
        return "emerging"
    if pop <= 30 or (followers is not None and followers < 5000):
        return "small"
    return "low_exposure"


def satisfies_filters(meta: SpotifyTrackMeta, *, min_freshness: float, max_exposure: int,
                       wanted_genres: list[str], wanted_countries: list[str],
                       release_from: date | None, release_to: date | None) -> bool:
    if release_from and meta.release_date and meta.release_date < release_from:
        return False
    if release_to and meta.release_date and meta.release_date > release_to:
        return False
    if wanted_genres and not (set(meta.genres) & set(wanted_genres)):
        return False
    if wanted_countries and meta.country not in wanted_countries:
        return False
    if freshness_score(meta.release_date) < min_freshness:
        return False
    if meta.popularity_signal > max_exposure:
        return False
    return True