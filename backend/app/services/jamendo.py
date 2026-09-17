"""Jamendo discovery provider — free CC-licensed music for *real* publication.

Jamendo exposes its catalog through an open API. Every track carries an
explicit Creative-Commons license, which is exactly what the autonomous
pipeline needs: we can legally obtain publication rights for a track
source without waiting on a human reply.
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
ALLOWED_LICENSES = {"by", "by-sa", "zero", "cc0", "cc"}

# Jamendo's tag vocabulary is broader than the app's default labels. Keep
# aliases here so a friendly genre such as "Lo-fi" does not become a
# zero-result API query.
TAG_ALIASES = {
    "lo-fi": ["lofi", "chillout", "chill", "downtempo"],
    "lofi": ["lofi", "chillout", "chill", "downtempo"],
    "ambient": ["ambient", "chillout", "atmospheric"],
    "electronic": ["electronic", "electronica", "dance"],
}


def license_allows(license_name: str) -> bool:
    raw = (license_name or "").strip().lower().replace(" ", "-")
    if not raw:
        return False
    if "/" in raw:
        raw = raw.rstrip("/").split("/")[-1]
    return bool(_first_code(raw.removeprefix("cc-")))


def _first_code(code: str) -> str:
    for part in code.split(";"):
        tokens = [t for t in part.replace(".", "-").split("-") if t]
        if not tokens:
            continue
        base = tokens[0]
        if base in ALLOWED_LICENSES and not ({"nc", "nd"} & set(tokens)):
            return base
    return ""


def license_code_from_url(ccurl: str) -> str:
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

    def _tags_for_genre(self, genre: str) -> list[str]:
        key = (genre or "").strip().lower()
        return TAG_ALIASES.get(key, [genre.strip()] if genre.strip() else [])

    def discover(self, *, genres: list[str], release_from: date,
                 release_to: date, limit: int = 30,
                 country: str | None = None) -> list[SpotifyTrackMeta]:
        """Discover enough valid tracks by trying aliases and API pages.

        Jamendo can return a small/empty page for a tag, and its tags are
        effectively ANDed when combined. We therefore query one tag at a
        time, paginate, and continue across aliases/genres until `limit`
        *license-valid, unique* tracks have been collected.
        """
        if limit <= 0:
            return []

        base = {
            "client_id": self.client_id,
            "format": "json",
            "include": "musicinfo",
            "audioformat": "mp32",
            "order": "popularity_week",
        }
        page_size = min(max(limit * 2, 20), 100)
        max_pages_per_tag = 5
        out: list[SpotifyTrackMeta] = []
        seen: set[str] = set()
        tags: list[str] = []
        for genre in genres or ["electronic", "ambient"]:
            for tag in self._tags_for_genre(genre):
                if tag and tag not in tags:
                    tags.append(tag)

        # If the caller supplied only unknown/empty tags, use broad fallback
        # tags instead of turning a scheduled run into a zero-candidate run.
        for tag in ["electronic", "ambient", "chillout", "instrumental"]:
            if tag not in tags:
                tags.append(tag)

        for tag in tags:
            if len(out) >= limit:
                break
            for page in range(max_pages_per_tag):
                offset = page * page_size
                params = dict(base, tags=tag, limit=str(page_size), offset=str(offset))
                try:
                    resp = self._http.get(API_BASE, params=params)
                    resp.raise_for_status()
                    payload = resp.json()
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("Jamendo query failed tag=%s page=%s: %s", tag, page + 1, exc)
                    break

                items = payload.get("results") or []
                if not items:
                    break
                for item in items:
                    if len(out) >= limit:
                        break
                    license_name = (
                        item.get("license_ccname")
                        or license_code_from_url(item.get("license_ccurl") or "")
                        or "unknown"
                    )
                    if not license_allows(license_name):
                        continue
                    meta = track_from_item(item)
                    if not meta.external_ids.get("audio_url"):
                        continue
                    if meta.spotify_track_id in seen:
                        continue
                    seen.add(meta.spotify_track_id)
                    out.append(meta)
                if len(items) < page_size:
                    break

        log.info("Jamendo discovery: %d valid candidates from %d tags", len(out), len(tags))
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
