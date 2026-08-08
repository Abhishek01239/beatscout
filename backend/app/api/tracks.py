"""Track endpoints: list, detail, reject."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Track, User
from ..schemas.spotify import TrackFilter, TrackOut
from .deps import get_current_user, own_track

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("", response_model=list[TrackOut])
def list_tracks(filters: TrackFilter = Depends(), db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    q = db.query(Track).filter(Track.user_id == current.id)
    if filters.status:
        q = q.filter(Track.status == filters.status)
    if filters.rights_status:
        q = q.filter(Track.rights_status == filters.rights_status)
    if filters.genre:
        q = q.filter(Track.genre.ilike(f"%{filters.genre}%"))
    if filters.country:
        q = q.filter(Track.country == filters.country)
    if filters.exposure:
        q = q.filter(Track.exposure_label == filters.exposure)
    if filters.search:
        term = f"%{filters.search}%"
        q = q.filter(Track.track_name.ilike(term) | Track.artist_name.ilike(term))
    return (q.order_by(Track.discovery_score.desc())
            .offset(filters.offset).limit(filters.limit).all())


@router.get("/{track_id}", response_model=TrackOut)
def track_detail(track_id: int, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    return own_track(db, track_id, current)


@router.post("/{track_id}/reject", response_model=TrackOut)
def reject_track(track_id: int, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    track = own_track(db, track_id, current)
    track.status = "REJECTED"
    db.commit()
    return track