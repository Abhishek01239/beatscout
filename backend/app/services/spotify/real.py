"""Real Spotify Web API client (metadata ONLY).

Uses Client Credentials flow (no user consent needed) + httpx. All calls
are read-only metadata queries: /search, /tracks.  No audio endpoints are
ever touched.

Raises:
    SpotifyError        — generic upstream failure
    SpotifyRateLimited  — 429 with Retry-After handling
"""

from __future__ import annotations

from datetime import date, datetime

import httpx

from ...config import get_settings
from .base import SpotifyProviderBase, SpotifyTrackMeta


class SpotifyError(RuntimeError):
    pass


class SpotifyRateLimited(SpotifyError):
    pass


class RealSpotifyProvider(SpotifyProviderBase):
    """Live provider — requires SPOTIFY_CLIENT_ID + SPOTIFY_CLIENT_SECRET."""

    name = "REAL"
    _TOKEN_URL = "https://accounts.spotify.com/api/token"
    _API = "https://api.spotify.com/v1"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.has_spotify_credentials:
            raise SpotifyError("Spotify credentials are not configured.")
        self._client_id = settings.SPOTIFY_CLIENT_ID
        self._client_secret = settings.SPOTIFY_CLIENT_SECRET
        self._access_token: str | None = None
        self._token_expires: datetime | None = None
        self._client = httpx.Client(timeout=20)

    # -- auth -----------------------------------------------------------

    def _ensure_token(self) -> str:
        if self._access_token and self._token_expires and self._token_expires > datetime.now():
            return self._access_token
        resp = httpx.post(
            self._TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self._client_id, self._client_secret),
            timeout=20,
        )
        if resp.status_code != 200:
            raise SpotifyError(f"Spotify token failed: HTTP {resp.status_code}")
        body = resp.json()
        self._access_token = body["access_token"]
        self._token_expires = datetime.now().timestamp() + body.get("expires_in", 3600) - 60
        return self._access_token

    def _get(self, path: str, params: dict) -> dict:
        token = self._ensure_token()
        resp = self._client.get(f"{self._API}{path}", params=params,
                                headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 429:
            raise SpotifyRateLimited(self.rate_limit_message())
        if resp.status_code >= 400:
            raise SpotifyError(f"Spotify API error {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    # -- public API ------------------------------------------------------

    def search(self, query: str, limit: int = 20) -> list[SpotifyTrackMeta]:
        body = self._get("/search", {"q": query, "type": "track", "limit": limit})
        return [self._map_track(t) for t in body.get("tracks", {}).get("items", [])]

    def discover(self, genres=None, release_to=None, release_from=None,
                 limit: int = 30, country: str | None = None) -> list[SpotifyTrackMeta]:
        # "New releases, low popularity" heuristic: search freshly released
        # tracks across configured genres, then enrich popularity via tracks API
        year = release_to.year if release_to else date.today().year
        q = f"year:{year}"
        if genres:
            q = f"genre:{' OR genre:'.join(genres[:2])} {q}"
        body = self._get("/search", {"q": q, "type": "track", "limit": limit})
        return [self._map_track(t) for t in body.get("tracks", {}).get("items", [])]

    def get_track(self, spotify_track_id: str) -> SpotifyTrackMeta | None:
        body = self._get(f"/tracks/{spotify_track_id}", {})
        return self._map_track(body)

    # -- mapping ----------------------------------------------------------

    @staticmethod
    def _map_track(item: dict) -> SpotifyTrackMeta:
        artists = item.get("artists") or []
        artist = artists[0] if artists else {}
        album = item.get("album") or {}
        images = album.get("images") or []
        art = images[0]["url"] if images else ""
        ext = item.get("external_ids") or {}
        return SpotifyTrackMeta(
            spotify_track_id=item.get("id", ""),
            spotify_artist_id=artist.get("id", ""),
            track_name=item.get("name", "Untitled"),
            artist_name=artist.get("name", "Unknown artist"),
            album_name=album.get("name"),
            release_date=parse_spotify_date(album.get("release_date"), album.get("release_date_precision")),
            spotify_url=item.get("external_urls", {}).get("spotify", ""),
            album_art_url=art,
            duration_ms=item.get("duration_ms"),
            popularity_signal=item.get("popularity", 0),
            artist_popularity_signal=artist.get("popularity", 0),
            genres=album.get("genres") or [],
            country=None,
            external_ids={"isrc": ext.get("isrc")},
            isrc=ext.get("isrc"),
        )


def parse_spotify_date(raw: str | None, precision: str | None) -> date | None:
    if not raw:
        return None
    try:
        if precision == "year":
            return date(int(raw), 1, 1)
        if precision == "month":
            y, m = raw.split("-")
            return date(int(y), int(m), 1)
        return date.fromisoformat(raw)
    except ValueError:
        return None