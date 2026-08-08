"""YouTube provider factory + upload orchestration service."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ...config import get_settings
from ...models import YouTubeAccount, YouTubeUpload
from .base import YouTubeProviderBase
from .mock import MockYouTubeProvider
from .real import RealYouTubeProvider

log = logging.getLogger("beatscout.youtube.svc")


def get_youtube_provider() -> YouTubeProviderBase:
    settings = get_settings()
    if settings.has_youtube_credentials:
        try:
            return RealYouTubeProvider()
        except Exception:
            log.warning("YouTube real provider failed to init, falling back to mock")
    return MockYouTubeProvider()


def connect_info(db: Session, user) -> dict:
    """Auth URL + status for the settings page."""
    provider = get_youtube_provider()
    account = db.query(YouTubeAccount).filter(YouTubeAccount.user_id == user.id).first()
    return {
        "provider": provider.name,
        "connected": bool(account and account.status == "connected"),
        "auth_url": provider.get_auth_url(),
        "channel": channel_out(account) if account else None,
    }


def channel_out(account: YouTubeAccount | None) -> dict | None:
    if not account:
        return None
    return {
        "channel_id": account.channel_id,
        "channel_name": account.channel_name,
        "subscriber_count": account.subscriber_count,
        "video_count": account.video_count,
        "status": account.status,
    }


def exchange_oauth_callback(db: Session, user, code: str) -> YouTubeAccount:
    provider = get_youtube_provider()
    tokens = provider.exchange_code(code)   # may raise; caller converts to 4xx
    info = provider.get_channel_info(tokens)

    account = db.query(YouTubeAccount).filter(YouTubeAccount.user_id == user.id).first()
    if account is None:
        account = YouTubeAccount(user_id=user.id)
        db.add(account)

    account.access_token = tokens.get("access_token")
    account.refresh_token = tokens.get("refresh_token")
    account.token_expires_at = (
        datetime.utcfromtimestamp(tokens["expires_at"])
        if tokens.get("expires_at") else None
    )
    account.channel_id = info.channel_id
    account.channel_name = info.channel_name
    account.subscriber_count = info.subscriber_count
    account.video_count = info.video_count
    account.status = "connected"
    db.commit()
    return account


def upload_video(db: Session, user, upload: YouTubeUpload, video,
                 *, title: str | None = None, description: str | None = None,
                 tags: list[str] | None = None, category: str = "Music",
                 privacy: str = "private", playlist_id: str | None = None,
                 scheduled_at=None) -> YouTubeUpload:
    """Upload `video` as `upload` via the active provider (mock or real)."""
    account = db.query(YouTubeAccount).filter(YouTubeAccount.user_id == user.id).first()
    if account is None or account.status != "connected":
        raise PermissionError("YouTube is not connected. Connect it first.")

    provider = get_youtube_provider()
    upload.status = "uploading"
    db.commit()
    try:
        result = provider.upload(
            tokens={"access_token": account.access_token, "refresh_token": account.refresh_token},
            file_path=video.file_path,
            title=title,
            description=description,
            tags=tags,
            category=category,
            privacy=privacy,
            thumbnail_path=video.thumbnail_path,
            scheduled_at=scheduled_at,
        )
        upload.youtube_video_id = result.video_id
        upload.youtube_url = result.url
        upload.status = "published" if privacy == "public" else "uploaded"
        upload.error = None
    except Exception as exc:
        upload.status = "failed"
        upload.error = str(exc)
        db.commit()
        raise
    db.commit()
    return upload