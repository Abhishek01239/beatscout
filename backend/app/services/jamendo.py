"""Jamendo discovery provider — free CC-licensed music for *real* publication.

Jamendo exposes its catalog through an open API. Every track carries an
explicit Creative-Commons license, which is exactly what the autonomous
pipeline needs: we can legally obtain publication rights for a track
*source* without waiting on a human reply (Spotify cannot provide this —
Spotify audio is not redistributable, which is why the app's human-review
flow uses it, and the autonomous flow uses Jamendo).

Usage in the daily GitHub Action:
    JAMENDO_CLIENT_ID=xxx  python -m app.auto --provider jamendo

API (public docs):
    GET https://api.jamendo.com/v3.0/tracks/
    ?client_id=ID&format=json&limit=N&include=musicinfo&order=popularity_week&tags=...
"""

from __future__ import annotations

import logging
from datetime import date

import httpx

from ..config import get_settings
from .spotify.base import SpotifyTrackMeta

log = logging.getLogger("beatscout.discovery.jamendo")

API_BASE = "https://api.jamendo.com/v3.0/tracks/"

# Licenses that allow commercial use + derivative works (our visualizers).
#   by    -> Attribution
#   by-sa -> Attribution-ShareAlike
#   zero  -> CC0
# Excluded: -nc (no commercial), -nd (no derivatives).
ALLOWED_LICENSES = {"by", "by-sa", "zero"}


def license_allows(license_name: str) -> bool:
    """True if a CC license token permits auto-publication by BeatScout.

    Tolerates API quirks: 'by 3.0', 'CC BY 4.0', 'by-nc', url fragments.
    """
    raw = (license_name or "").strip().lower().replace(" ", "-")
    if not raw:
        return False
    if "/" in raw:
        raw = raw.rstrip("/").split("/")[-1]
    code = raw.removeprefix("cc-")
    return bool(_first_code(code))


def _first_code(code: str) -> str:
    """'by' | 'by-4.0' | 'CC-BY' -> 'by'; 'by-nc', 'by-nd', 'by-nc-sa' -> ''."""
    for part in code.split(";"):  # some endpoints return 'by;by-sa'
        tokens = [t for t in part.replace(".", "-").split("-") if t]
        if not tokens:
            continue
        base = tokens[0]
        if base in ALLOWED_LICENSES and not ({"nc", "nd"} & set(tokens)):
            return base
    return ""


def license_code_from_url(ccurl: str) -> str:
    """'https://creativecommons.org/licenses/by/3.0/' -> 'by'."""
    url = (ccurl or "").rstrip("/")
    if not url:
        return ""
    for frag in reversed(url.lower().split("/")):
        if frag in ALLOWED_LICENSES:
            return frag
    return ""


def track_from_item(item: dict) -> SpotifyTrackMeta:
    jam_id = str(item.get("id", ""))
    tags = item.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    license_url = item.get("license_ccurl") or ""
    license_name = item.get("license_ccname") or license_code_from_url(license_url) or "unknown"
    release = item.get("releasedate")
    rdate = None
    if release:
        try:
            rdate = date.fromisoformat(release[:10])
        except ValueError:
            rdate = None
    return SpotifyTrackMeta(
        spotify_track_id="jamendo:" + jam_id,
        spotify_artist_id="jamendo-art:" + str(item.get("artist_id") or jam_id),
        track_name=item.get("name") or "Untitled",
        artist_name=item.get("artist_name") or "Unknown Artist",
        album_name=item.get("album_name"),
        release_date=rdate,
        spotify_url=item.get("page") or "",
        album_art_url=item.get("image") or "",
        duration_ms=int(item.get("duration", 0) * 1000) if item.get("duration") else None,
        popularity_signal=int(item.get("popularity", 0) or 0),
        genres=tags,
        external_ids={
            "jamendo_id": jam_id,
            "audio_url": item.get("audio") or "",
            "license_url": license_url,
            "license_name": license_name,
            "album_id": str(item.get("album_id", "")),
        },
    )


class JamendoProvider:
    """Real discovery provider: free CC-licensed tracks via the Jamendo API."""

    name = "JAMENDO"

    def __init__(self, client_id: str | None = None) -> None:
        settings = get_settings()
        self.client_id = client_id or settings.JAMENDO_CLIENT_ID
        if not self.client_id:
            raise ValueError("JAMENDO_CLIENT_ID is required for Jamendo discovery.")
        self._http = httpx.Client(timeout=30.0, follow_redirects=True)

    # -- provider interface (mirrors Spotify) ---------------------------

    def discover(self, *, genres: list[str], release_from: date,
                 release_to: date, limit: int = 30,
                 country: str | None = None) -> list[SpotifyTrackMeta]:
        params = {
            "client_id": self.client_id,
            "format": "json",
            "limit": max(10, min(limit * 3, 200)),  # over-fetch, license-filter
            "include": "musicinfo",
            "audioformat": "mp32",
            "order": "popularity_week",
        }
        if genres:
            params["tags"] = ",".join(genres)
        resp = self._http.get(API_BASE, params=params)
        resp.raise_for_status()
        items = resp.json().get("results") or []
        out: list[SpotifyTrackMeta] = []
        for item in items:
            license_name = (
                item.get("license_ccname")
                or license_code_from_url(item.get("license_ccurl") or "")
                or "unknown"
            )
            if not license_allows(license_name):
                continue
            out.append(track_from_item(item))
            if len(out) >= limit:
                break
        return out

    def search(self, query: str, limit: int = 20) -> list[SpotifyTrackMeta]:
        return self.discover(genres=[query], release_from=date(2000, 1, 1),
                             release_to=date.today(), limit=limit)

    def get_track(self, spotify_track_id: str) -> SpotifyTrackMeta | None:
        jam_id = spotify_track_id.removeprefix("jamendo:")
        resp = self._http.get(API_BASE, params={
            "client_id": self.client_id, "format": "json", "id": jam_id,
        })
        if resp.status_code != 200:
            return None
        items = resp.json().get("results") or []
        return track_from_item(items[0]) if items else None

    def rate_limit_message(self) -> str:
        return "Jamendo API rate limit exceeded. Retry later."

    def close(self) -> None:
        self._http.close()