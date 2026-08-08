"""Mock YouTube provider — simulates OAuth + uploads for demo/offline use."""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

from .base import UploadResult, YouTubeChannelInfo, YouTubeProviderBase


class MockYouTubeProvider(YouTubeProviderBase):
    name = "MOCK"

    def get_auth_url(self) -> str:
        # In the mock, the frontend "Connect YouTube" button calls
        # POST /youtube/connect, gets this URL, and we simulate consent
        # automatically by exchanging a fake code (see exchange_code).
        state = uuid.uuid4().hex[:8]
        return f"https://accounts.google.com/o/oauth2/mock?state={state}"

    def exchange_code(self, code: str) -> dict:
        if not code:
            raise ValueError("missing mock OAuth code")
        return {
            "access_token": f"mock-yt-{uuid.uuid4().hex[:24]}",
            "refresh_token": f"mock-yt-refresh-{uuid.uuid4().hex[:16]}",
            "expires_at": int(datetime.now(timezone.utc).timestamp()) + 3600,
            "mock": True,
        }

    def get_channel_info(self, tokens: dict) -> YouTubeChannelInfo:
        rng = random.Random(1)
        return YouTubeChannelInfo(
            channel_id="UC-mock-channel-0001",
            channel_name="BeatScout Demo Channel",
            subscriber_count=rng.randint(120, 4000),
            video_count=rng.randint(5, 40),
        )

    def upload(self, tokens: dict, file_path: str, *, title: str, description: str,
               tags: list[str], category: str, privacy: str,
               thumbnail_path: str | None = None, scheduled_at=None) -> UploadResult:
        vid = f"mock-video-{uuid.uuid4().hex[:10]}"
        return UploadResult(
            video_id=vid,
            url=f"https://www.youtube.com/watch?v={vid}",
            status="uploaded",
        )