"""Spotify discovery endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas.spotify import DiscoverRequest, DiscoverResult, TrackOut
from ..services.discovery import DiscoveryConfig, discover_and_persist
from ..services.spotify import GENRES, get_spotify_provider
from .deps import get_current_user

log = logging.getLogger("beatscout.api.spotify")
router = APIRouter(prefix="/spotify", tags=["spotify"])


@router.get("/status")
def spotify_status(current: User = Depends(get_current_user)):
    provider = get_spotify_provider()
    return {"provider": provider.name, "configured": provider.name == "REAL"}


@router.get("/genres")
def genres(current: User = Depends(get_current_user)):
    return GENRES


@router.get("/search", response_model=list[TrackOut])
def search(q: str = Query(min_length=1, max_length=120), limit: int = Query(10, ge=1, le=50),
           db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """Search the active provider (mock or real) — returns *metadata only*."""
    provider = get_spotify_provider()
    try:
        results = provider.search(q, limit=limit)
    except Exception as exc:
        raise HTTPException(502, f"Spotify API unavailable: {exc}") from exc
    # Return as ephemeral TrackOut rows (not persisted)
    return [_meta_to_out(m, index=i) for i, m in enumerate(results)]


@router.post("/discover", response_model=DiscoverResult)
def discover(body: DiscoverRequest, db: Session = Depends(get_db),
             current: User = Depends(get_current_user)):
    """Run one discovery scan for the current user. Metadata-only."""
    try:
        cfg = DiscoveryConfig(
            release_window_days=body.release_window_days,
            genres=body.genres,
            countries=body.countries,
            max_tracks=body.max_tracks,
            min_freshness=body.min_freshness,
            max_artist_exposure=body.max_artist_exposure,
            min_release_date=body.min_release_date,
        )
        result = discover_and_persist(db, current.id, cfg)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Discovery failed: {exc}")
    return result


def _meta_to_out(meta, exists: bool) -> TrackOut:
    from datetime import datetime
    return TrackOut(
        id=-1, spotify_track_id=meta.spotify_track_id, track_name=meta.track_name,
        artist_name=meta.artist_name, album_name=meta.album_name,
        release_date=meta.release_date, spotify_url=meta.spotify_url,
        album_art_url=meta.album_art_url, duration_ms=meta.duration_ms,
        genre=", ".join(meta.genres[:2]), country=meta.country,
        discovery_score=0.0, exposure_label="candidate", status="NEW",
        rights_status="UNKNOWN", created_at=datetime.now(),
    )