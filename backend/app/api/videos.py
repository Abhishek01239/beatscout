"""Video endpoints: generate, preview, list, detail, status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Track, User, Video
from ..schemas.video import TemplateList, VideoOut, VideoPreviewRequest, VideoRenderRequest
from ..services.rights import BUSINESS_RULE_MESSAGE
from ..services.video.service import render_for_track
from .deps import get_current_user, own_track

router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("/templates", response_model=list[TemplateList])
def templates(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    from ..models import VideoTemplate
    rows = db.query(VideoTemplate).all()
    if not rows:  # fall back to built-ins when templates not seeded
        from ..services.video.engine import STYLE_DEFAULTS
        return [TemplateList(id=i, name=k, label=k.capitalize(),
                             description=v["description"], defaults=v["defaults"])
                for i, (k, v) in enumerate(STYLE_DEFAULTS.items())]
    return rows


@router.post("/generate", response_model=VideoOut)
def generate(body: VideoRenderRequest, db: Session = Depends(get_db),
             current: User = Depends(get_current_user)):
    """Render a video for a track.

    Enforces the rights gate: raises 403 unless rights_status == APPROVED.
    """
    track = own_track(db, body.track_id, current)
    try:
        video = render_for_track(db, track, style=body.template,
                                 settings=body.settings, as_preview=body.preview)
    except PermissionError:
        raise HTTPException(403, BUSINESS_RULE_MESSAGE)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return video


@router.post("/preview", response_model=VideoOut)
def preview(body: VideoPreviewRequest, db: Session = Depends(get_db),
            current: User = Depends(get_current_user)):
    """Short low-res preview render (same rights gate)."""
    track = own_track(db, body.track_id, current)
    try:
        video = render_for_track(db, track, style=body.template,
                                 settings=body.settings, as_preview=True)
    except PermissionError:
        raise HTTPException(403, BUSINESS_RULE_MESSAGE)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return video


@router.get("", response_model=list[VideoOut])
def list_videos(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return (db.query(Video).filter(Video.user_id == current.id)
            .order_by(Video.created_at.desc()).limit(100).all())


@router.get("/{video_id}", response_model=VideoOut)
def video_detail(video_id: int, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    video = db.get(Video, video_id)
    if video is None or video.user_id != current.id:
        raise HTTPException(404, "Video not found")
    return video


@router.get("/{video_id}/status", response_model=VideoOut)
def video_status(video_id: int, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    return video_detail(video_id, db, current)