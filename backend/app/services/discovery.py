"""Discovery orchestration: provider -> filter -> score -> persist."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models import Artist, Track
from .spotify import (
    discovery_score,
    exposure_label,
    get_spotify_provider,
    satisfies_filters,
)
from .spotify.base import SpotifyTrackMeta

log = logging.getLogger("beatscout.discovery")


class DiscoveryConfig:
    """Mirror of the user-adjustable discovery knobs."""

    def __init__(self, *, release_window_days: int = 90, genres: list[str] | None = None,
                 countries: list[str] | None = None, max_tracks: int = 30,
                 min_freshness: float = 0.0, max_artist_exposure: int = 40,
                 min_release_date: date | None = None, spotify_limit: int = 50) -> None:
        self.release_window_days = release_window_days
        self.genres = genres or []
        self.countries = countries or []
        self.max_tracks = max_tracks
        self.min_freshness = min_freshness
        self.max_artist_exposure = max_artist_exposure
        self.min_release_date = min_release_date
        self.spotify_limit = spotify_limit

    def release_from(self) -> date:
        if self.min_release_date:
            return self.min_release_date
        return date.today() - timedelta(days=self.release_window_days)


def discover_and_persist(db: Session, user_id: int, cfg: DiscoveryConfig) -> dict:
    """Run one discovery pass and persist new tracks for the user.

    Returns a summary dict (discovered / new_tracks / scoring_summary).
    """
    provider = get_spotify_provider()
    release_from = cfg.release_from()
    log.info("Spotify discovery started (provider=%s window=%dd genres=%s)",
             provider.name, cfg.release_window_days, cfg.genres)

    metas = provider.discover(
        genres=cfg.genres,
        release_from=release_from,
        release_to=date.today(),
        limit=cfg.spotify_limit,
    )
    log.info("%d tracks discovered", len(metas))

    # Filter + score
    candidates = [
        m for m in metas
        if satisfies_filters(
            m,
            min_freshness=cfg.min_freshness,
            max_exposure=cfg.max_artist_exposure,
            wanted_genres=cfg.genres,
            wanted_countries=cfg.countries,
            release_from=release_from,
            release_to=None,
        )
    ]
    scored = [(m, discovery_score(m, cfg.genres)) for m in candidates]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    scored = scored[: cfg.max_tracks]

    new_count = 0
    for meta, score in scored:
        existing = None
        if meta.spotify_track_id:
            existing = db.query(Track).filter(
                Track.spotify_track_id == meta.spotify_track_id,
                Track.user_id == user_id,
            ).first()
        if existing:
            continue

        artist = get_or_create_artist(db, meta)
        track = Track(
            user_id=user_id,
            spotify_track_id=meta.spotify_track_id or None,
            artist_id=artist.id if artist else None,
            track_name=meta.track_name,
            artist_name=meta.artist_name,
            album_name=meta.album_name,
            release_date=meta.release_date,
            spotify_url=meta.spotify_url,
            album_art_url=meta.album_art_url,
            duration_ms=meta.duration_ms,
            external_ids=meta.external_ids,
            genre=", ".join(meta.genres) if meta.genres else None,
            country=meta.country,
            discovery_score=score,
            exposure_label=exposure_label(meta),
            source="spotify",
            status="NEW",
            rights_status="UNKNOWN",
        )
        db.add(track)
        new_count += 1

    db.commit()
    log.info("%d new tracks persisted", new_count)
    return {
        "discovered": len(metas),
        "new_tracks": new_count,
        "scoring_summary": {
            "provider": provider.name,
            "candidates": len(scored),
            "score_range": [scored[0][1], scored[-1][1]] if scored else [0, 0],
        },
    }


def get_or_create_artist(db: Session, meta: SpotifyTrackMeta) -> Artist | None:
    if not meta.spotify_artist_id and not meta.artist_name:
        return None
    artist = None
    if meta.spotify_artist_id:
        artist = db.query(Artist).filter(Artist.spotify_artist_id == meta.spotify_artist_id).first()
    if artist is None:
        artist = db.query(Artist).filter(Artist.name == meta.artist_name).first()
    if artist is None:
        artist = Artist(
            spotify_artist_id=meta.spotify_artist_id or None,
            name=meta.artist_name,
            genres=meta.genres,
            popularity_signal=meta.artist_popularity_signal,
            followers_signal=meta.artist_followers_signal,
            country=meta.country,
        )
        db.add(artist)
        db.flush()
    return artist