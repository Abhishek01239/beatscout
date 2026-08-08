"""YouTube Data API v3 integration.

Two providers:
  - ``MockYouTubeProvider`` — offline demo/simulation (OAuth connect +
    uploads), used automatically when YOUTUBE_CLIENT_ID is missing.
  - ``RealYouTubeProvider`` — OAuth 2.0 web flow + resumable upload via
    ``google-api-python-client`` / ``google-auth-oauthlib``.

Secrets are stored encrypted at rest (see ``app.security``) and never
exposed through the API. Real uploads default to ``private``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

log = logging.getLogger("beatscout.youtube")


@dataclass
class YouTubeChannelInfo:
    channel_id: str
    channel_name: str
    subscriber_count: int
    video_count: int


@dataclass
class UploadResult:
    video_id: str
    url: str
    status: str = "uploaded"


class YouTubeProviderBase:
    name: str = "base"

    def get_auth_url(self) -> str:
        raise NotImplementedError

    def exchange_code(self, code: str) -> dict:
        """Return {access_token, refresh_token, expires_in}."""
        raise NotImplementedError

    def get_channel_info(self, tokens: dict) -> YouTubeChannelInfo:
        raise NotImplementedError

    def upload(self, tokens: dict, file_path: str, *, title: str, description: str,
               tags: list[str], category: str, privacy: str,
               thumbnail_path: str | None = None, scheduled_at=None) -> UploadResult:
        raise NotImplementedError