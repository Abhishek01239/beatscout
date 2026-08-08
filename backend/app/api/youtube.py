"""YouTube endpoints: connect (OAuth), callback, upload, channel, uploads."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Track, User, Video, YouTubeUpload
from ..schemas.youtube import (
    MetadataPreview, UploadRequest, YouTubeChannelOut, YouTubeUploadOut,
)
from ..services import metadata as metadata_svc
from ..services.youtube import (
    connect_info, exchange_oauth_callback, upload_video,
    get_youtube_provider,
)
from .deps import get_current_user

log = logging.getLogger("beatscout.api.youtube")
router = APIRouter(prefix="/youtube", tags=["youtube"])


@router.get("/status")
def status(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return connect_info(db, current)


@router.post("/connect")
def connect(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Begin OAuth — returns the auth URL the user must open."""
    provider = get_youtube_provider()
    if provider.name == "MOCK":
        # mock consent: immediately exchange a synthetic code
        result = exchange_oauth_callback(db, current, code="mock-consent-granted")
        return {"url": None, "connected": True, "channel": connect_info(db, current)["channel"]}
    return {"url": provider.get_auth_url(), "connected": False}


@router.post("/callback")
def callback(code: str, current: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """Exchange the OAuth code (mock or real)."""
    try:
        account = exchange_oauth_callback(db, current, code)
    except Exception as exc:
        raise HTTPException(401, f"YouTube authentication failed: {exc}")
    return {"connected": True, "channel": account.channel_name}


@router.get("/channel", response_model=YouTubeChannelOut)
def channel(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    info = connect_info(db, current)
    if not info["connected"] or info["channel"] is None:
        raise HTTPException(404, "YouTube not connected")
    return info["channel"]


@router.post("/upload", response_model=YouTubeUploadOut)
def upload(body: UploadRequest, current: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    """Upload a rendered video to YouTube (mock or real). Default privacy=private."""
    video = db.get(Video, body.video_id)
    if video is None or video.user_id != current.id:
        raise HTTPException(404, "Video not found")
    if video.status != "completed":
        raise HTTPException(422, "Video is not rendered yet (status: %s)" % video.status)

    track = db.get(Track, video.track_id)
    meta = metadata_svc.build_youtube_metadata(track, track.license) if track else {}

    title = body.title or meta.get("title", f"{video.template} visualizer")
    description = body.description or meta.get("description", "")
    tags = body.tags or meta.get("tags", [])
    upload_row = YouTubeUpload(
        user_id=current.id,
        track_id=video.track_id,
        video_id=video.id,
        title=title,
        description=description,
        tags=tags,
        category=body.category,
        privacy=body.privacy,
        scheduled_at=body.scheduled_at,
        playlist_id=body.playlist_id,
        thumbnail_path=video.thumbnail_path,
        status="draft",
    )
    db.add(upload_row)
    db.commit()
    db.refresh(upload_row)

    try:
        result = upload_video(db, current, upload_row, video,
                              title=title, description=description, tags=tags,
                              category=body.category, privacy=body.privacy,
                              scheduled_at=body.scheduled_at)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"YouTube upload failed: {exc}")
    return result


@router.get("/uploads", response_model=list[YouTubeUploadOut])
def uploads(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (db.query(YouTubeUpload).filter(YouTubeUpload.user_id == current.id)
            .order_by(YouTubeUpload.created_at.desc()).limit(100).all())


@router.get("/metadata/preview", response_model=MetadataPreview)
def metadata_preview(track_id: int, current: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    from .deps import own_track
    track = own_track(db, track_id, current)
    meta = metadata_svc.build_youtube_metadata(track, track.license)
    meta["disclaimers"] += [
        "Generated with permission of the artist/license owner."
    ]
    return meta