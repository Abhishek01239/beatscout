"""Video render service: rights gate -> thumbnail -> render -> persist."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from ...config import get_settings
from ...models import AudioSource, License, Track, Video
from ..rights import require_approved_rights
from .engine import TEMPLATES, DisplayInfo, render_video
from .thumbnail import render_thumbnail

log = logging.getLogger("beatscout.video.service")


def render_for_track(
    db: Session,
    track: Track,
    *,
    style: str = "minimal",
    settings: dict | None = None,
    as_preview: bool = False,
    progress=None,
) -> Video:
    """Render a visualizer video for an APPROVED track.

    Raises PermissionError when rights are not APPROVED (business rule).
    """
    require_approved_rights(track)

    audio = track.audio_source
    if audio is None or not Path(audio.file_path).exists():
        raise ValueError("This track has no legally obtained audio file. Add audio first.")

    from ..artwork import ensure_artwork
    art_path = ensure_artwork(track)
    if not art_path or not Path(art_path).exists():
        raise ValueError("No artwork available for this track.")

    style = style if style in TEMPLATES else "minimal"
    settings = settings or {}
    cfg = get_settings()

    if as_preview:
        width, height = cfg.PREVIEW_WIDTH, cfg.PREVIEW_HEIGHT
        fps = 24
        preview_seconds = 8.0
    else:
        width, height = cfg.VIDEO_WIDTH, cfg.VIDEO_HEIGHT
        fps = min(60, max(12, int(settings.get("fps", cfg.VIDEO_FPS))))
        preview_seconds = None

    video = Video(
        user_id=track.user_id,
        track_id=track.id,
        template=style,
        status="rendering",
        progress=0.0,
        width=width,
        height=height,
        fps=fps,
        settings=settings,
        preview=as_preview,
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    media_root = get_settings().storage_dir / "video"
    media_root.mkdir(parents=True, exist_ok=True)
    out_path = media_root / f"video_{video.id}{'_preview' if as_preview else ''}.mp4"
    thumb_path = media_root / f"thumb_{video.id}.jpg"

    try:
        license_row = db.query(License).filter(License.track_id == track.id).first()
        attribution = license_row.attribution_text if license_row and license_row.attribution_required else None
        meta = render_video(
            DisplayInfo(title=track.track_name, artist=track.artist_name, attribution=attribution),
            audio.file_path,
            art_path,
            style,
            out_path=str(out_path),
            width=width,
            height=height,
            fps=fps,
            settings={
                **settings,
                "title": track.track_name,
                "artist": track.artist_name,
                "attribution": attribution or "",
            },
            preview_seconds=preview_seconds,
            progress=lambda p: update_progress(db, video.id, p),
        )
        render_thumbnail(track, str(thumb_path), layout=settings.get("layout", "classic"))

        video.file_path = str(out_path)
        video.thumbnail_path = str(thumb_path)
        video.duration_ms = meta["duration_ms"]
        video.status = "completed"
        video.progress = 1.0
        video.completed_at = __import__("datetime").datetime.utcnow()
        db.commit()
        track.status = "VIDEO_GENERATED"
        db.commit()
        return video
    except Exception as exc:
        update_progress(db, video.id, 0.0, error=str(exc), status="failed")
        log.exception("render failed for track %s", track.id)
        raise


def update_progress(db: Session, video_id: int, progress: float, error: str | None = None,
                    status: str | None = None) -> None:
    db.query(Video).filter(Video.id == video_id) \
        .update({
            "progress": round(min(max(progress, 0), 1), 3),
            **({"error": error} if error else {}),
            **({"status": status} if status else {}),
        }, synchronize_session=False)
    db.commit()


def video_ready_for_upload(video: Video) -> bool:
    return video.status == "completed" and bool(video.file_path and Path(video.file_path).exists())