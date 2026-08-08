"""Real YouTube Data API v3 provider (optional dependency).

Requires:
    pip install google-api-python-client google-auth-oauthlib

and YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REDIRECT_URI.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ...config import get_settings
from .base import UploadResult, YouTubeChannelInfo, YouTubeProviderBase

log = logging.getLogger("beatscout.youtube.real")


class RealYouTubeProvider(YouTubeProviderBase):
    name = "REAL"

    @staticmethod
    def _check_deps() -> None:
        try:
            import google.auth.transport.requests  # noqa: F401
            import google.oauth2.credentials  # noqa: F401
            import google_auth_oauthlib.flow  # noqa: F401
            import googleapiclient.discovery  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Real YouTube needs extra deps: pip install google-api-python-client google-auth-oauthlib"
            ) from exc

    def _credentials(self, tokens: dict):
        from google.oauth2.credentials import Credentials
        return Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=get_settings().YOUTUBE_CLIENT_ID,
            client_secret=get_settings().YOUTUBE_CLIENT_SECRET,
        )

    def get_auth_url(self) -> str:
        self._check_deps()
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": get_settings().YOUTUBE_CLIENT_ID,
                    "client_secret": get_settings().YOUTUBE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [get_settings().YOUTUBE_REDIRECT_URI],
                }
            },
            scopes=[
                "https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube.readonly",
                "https://www.googleapis.com/auth/youtubepartner",
            ],
        )
        flow.redirect_uri = get_settings().YOUTUBE_REDIRECT_URI
        url, _ = flow.authorization_url(access_type="offline", prompt="consent")
        return url

    def exchange_code(self, code: str) -> dict:
        self._check_deps()
        from google_auth_oauthlib.flow import Flow

        settings = get_settings()
        flow = Flow(
            client_config={
                "web": {
                    "client_id": settings.YOUTUBE_CLIENT_ID,
                    "client_secret": settings.YOUTUBE_CLIENT_SECRET,
                    "auth_uris": ["https://accounts.google.com/o/oauth2/auth"],
                    "token_uris": ["https://oauth2.googleapis.com/token"],
                    "redirect_uris": [settings.YOUTUBE_REDIRECT_URI],
                }
            },
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )
        flow.redirect_uri = settings.YOUTUBE_REDIRECT_URI
        flow.fetch_token(code=code)
        creds = flow.credentials
        return {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expires_at": creds.expiry.timestamp() if creds.expiry else None,
            "mock": False,
        }

    def get_channel_info(self, tokens: dict) -> YouTubeChannelInfo:
        self._check_deps()
        from googleapiclient.discovery import build

        self._refresh(tokens)
        yt = build("youtube", "v3", credentials=self._credentials(tokens))
        resp = yt.channels().list(part="snippet,statistics", mine=True).execute()
        item = resp["items"][0]
        return YouTubeChannelInfo(
            channel_id=item["id"],
            channel_name=item["snippet"]["title"],
            subscriber_count=int(item["statistics"].get("subscriberCount", 0)),
            video_count=int(item["statistics"].get("videoCount", 0)),
        )

    def upload(self, tokens: dict, file_path: str, *, title: str, description: str,
               tags: list[str], category: str, privacy: str,
               thumbnail_path: str | None = None, scheduled_at=None) -> UploadResult:
        self._check_deps()
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        self._refresh(tokens)
        yt = build("youtube", "v3", credentials=self._credentials(tokens))
        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:4900],
                "tags": tags[:30],
                "categoryId": category,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }
        if scheduled_at:
            body["status"]["publishAt"] = scheduled_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            body["status"]["privacyStatus"] = "private"
        media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True,
                                chunksize=8 * 1024 * 1024)
        request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = None
        while resp is None:  # resumable loop
            status, resp = request.next_chunk()
            if status:
                log.info("upload progress %d%%", int(status.progress() * 100))
        vid = resp["id"]
        if thumbnail_path:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(thumbnail_path)).execute()
        return UploadResult(video_id=vid, url=f"https://www.youtube.com/watch?v={vid}")

    # -- helpers ------------------------------------------------------------

    def _credentials(self, tokens: dict):
        from google.oauth2.credentials import Credentials
        return Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=get_settings().YOUTUBE_CLIENT_ID,
            client_secret=get_settings().YOUTUBE_CLIENT_SECRET,
        )

    def _refresh(self, tokens: dict) -> None:
        from google.auth.transport.requests import Request

        creds = self._credentials(tokens)
        creds.refresh(Request())